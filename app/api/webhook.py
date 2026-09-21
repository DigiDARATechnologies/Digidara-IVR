import asyncio
from fastapi import APIRouter, Request, Form, Depends
from typing import Optional
import pymysql
import os
import requests
from app.database.db import get_db
from app.services import call_log_service

router = APIRouter(tags=["Webhooks"])

@router.post("/webhook/twilio")
async def twilio_webhook(
    request: Request,
    CallSid: Optional[str] = Form(None),
    CallStatus: Optional[str] = Form(None),
    CallDuration: Optional[int] = Form(None),
    db: pymysql.Connection = Depends(get_db)
):
    data = await request.form()
    print("TWILIO WEBHOOK RECEIVED")
    print(dict(data))
    
    # Log to workspace directory file for debugging
    try:
        import datetime
        import os
        project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        log_dir = os.path.join(project_dir, "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "webhook_requests.log")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.datetime.now()}] {dict(data)}\n")
    except Exception as e:
        print("Failed to write webhook log:", str(e))
        
    sid = CallSid or data.get("CallSid")
    status = CallStatus or data.get("CallStatus")
    
    # Duration might come as a string
    duration_str = data.get("CallDuration") or data.get("Duration")
    duration = CallDuration
    if duration_str and duration is None:
        try:
            duration = int(duration_str)
        except ValueError:
            duration = 0
            
    if duration is None:
        duration = 0
    
    if sid and status:
        final_statuses = ["completed", "busy", "no-answer", "canceled", "failed"]
        try:
            if status.lower() in final_statuses:
                updated = await asyncio.to_thread(call_log_service.finalize_call_log, db, sid, status, duration)
            else:
                updated = await asyncio.to_thread(call_log_service.update_call_log_status, db, sid, status)
        except Exception as e:
            import traceback
            print(f"Error processing Twilio webhook for sid={sid}, status={status}, duration={duration}: {e}")
            traceback.print_exc()
            raise

        if updated:
            return {"status": "success", "call_log": updated}

    return {"status": "success"}

@router.post("/webhook/twilio/recording")
async def twilio_recording_webhook(request: Request, db: pymysql.Connection = Depends(get_db)):
    """Persist the final dual-channel recording metadata for later playback."""
    data = await request.form()
    sid, recording_sid = data.get("CallSid"), data.get("RecordingSid")
    if sid and recording_sid:
        cur = db.cursor()
        cur.execute(
            """UPDATE call_logs SET recording_sid=%s, recording_status=%s,
               recording_duration_seconds=%s, recording_channels=%s
               WHERE call_sid=%s""",
            (recording_sid, data.get("RecordingStatus") or "completed",
             int(data.get("RecordingDuration") or 0), int(data.get("RecordingChannels") or 2), sid),
        )
        db.commit()
        # The recording callback usually arrives after Twilio has calculated call price.
        account_sid, token = os.getenv("TWILIO_ACCOUNT_SID", ""), os.getenv("TWILIO_AUTH_TOKEN", "")
        if account_sid and token:
            try:
                response = await asyncio.to_thread(requests.get,
                    f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Calls/{sid}.json",
                    auth=(account_sid, token), timeout=10)
                price = abs(float((response.json() if response.ok else {}).get("price") or 0))
                cur.execute("UPDATE call_logs SET estimated_twilio_cost_usd=%s WHERE call_sid=%s", (price, sid))
                db.commit()
            except Exception as exc:
                print(f"Twilio price lookup pending for {sid}: {exc}")
    return {"status": "success"}
