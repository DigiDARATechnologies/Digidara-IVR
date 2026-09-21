import pymysql
import os
import uuid
import requests
from requests.exceptions import RequestException, Timeout
from fastapi import APIRouter, Depends, File, Form, HTTPException, status, Request, Response, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from typing import List, Optional
from dotenv import load_dotenv
from app.database.db import get_db, get_db_connection
from app.schemas.call import CallStartRequest, CallStartResponse, SheetCallRequest
from app.schemas.call_log import CallLogResponse
from app.services.call_guardrail_service import with_call_guardrails
from app.services import customer_service, campaign_service, telephony_service, call_log_service, google_sheets_service, bulk_upload_service
from app.api.auth import current_admin
from app.services.telephony import get_telephony_provider
from app.services import audio_utils
from app.services.conversation_service import save_conversation
import json
import base64
import asyncio
import struct
import re
import threading
import shutil
import subprocess
import tempfile
from pathlib import Path
from difflib import SequenceMatcher



router = APIRouter(tags=["Calls"])
load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env")), override=True)
TAMIL_TTS_SPEAKER = os.getenv("TAMIL_TTS_SPEAKER", "Kore").strip() or "Kore"

# Tamil call regression checklist:
# 1. Turn 2 answers the customer's turn-2 question, not turn 1.
# 2. Turn 5 keeps up to 10 recent history messages plus system context.
# 3. Same customer_id has no duplicate conversation rows per turn.
# 4. Greeting and all Tamil responses use TAMIL_TTS_SPEAKER.
# 5. media_stream rejects Tamil customer_id connections immediately.
# 6. voice_respond skips RecordingUrl download whenever SpeechResult exists.


def get_optional_db():
    conn = None
    try:
        conn = get_db_connection()
    except Exception as e:
        print(f"[voice] Database unavailable: {e}")
        yield None
        return

    try:
        yield conn
    finally:
        conn.close()


def voice_error_response(
    message: str = "Sorry, our voice assistant is temporarily unavailable. Please try again later.",
    lang_code: str = "en-IN",
    hangup: bool = True,
) -> Response:
    say_xml = get_say_xml(message, lang_code)
    hangup_xml = "\n    <Hangup />" if hangup else ""
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    {say_xml}{hangup_xml}
</Response>"""
    return Response(content=twiml, media_type="application/xml")


def _looks_tamil_or_tanglish(text: str) -> bool:
    lower = (text or "").lower()
    if any("\u0b80" <= ch <= "\u0bff" for ch in text):
        return True
    markers = [
        "aam", "ama", "venum", "vendum", "reminder", "call", "course",
        "join", "joining", "naala", "nalai", "thingal", "monday", "yes", "no",
    ]
    return any(marker in lower for marker in markers)


def _normalize_voice_text(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"[\s\W_]+", "", text, flags=re.UNICODE)
    return text


def _is_assistant_echo_or_noise(text: str) -> bool:
    """Reject transcripts that are likely the assistant's own Tamil reprompt or noise."""
    normalized = _normalize_voice_text(text)
    raw_compact = re.sub(r"\s+", "", (text or "").strip().lower())
    if not normalized:
        return True
    echo_markers = [
        "மன்னிக்கவும்",
        "சரியாககேட்கவில்லை",
        "மீண்டும்கூறவும்",
        "மீண்டும்சொல்ல",
        "இன்னொருமுறைதெளிவாக",
        "எஸ்பிஐ",
        "கிரெடிட்கார்டு",
        "creditcard",
        "sbicredit",
        "repeat",
        "couldyourepeat",
        "ididntcatch",
    ]
    if any(marker in normalized or marker in raw_compact for marker in echo_markers):
        return True

    words = (text or "").strip().split()
    if len(words) >= 4:
        unique_ratio = len(set(words)) / max(len(words), 1)
        if unique_ratio <= 0.35:
            return True
    return False


def _should_reject_stt(text: str, confidence) -> bool:
    clean = (text or "").strip()
    if not clean:
        return True
    if _is_assistant_echo_or_noise(clean):
        return True
    try:
        conf = float(confidence) if confidence is not None else None
    except (TypeError, ValueError):
        conf = None
    hard_min = float(os.getenv("GEMINI_HARD_MIN_STT_CONFIDENCE", "0.12"))
    soft_min = float(os.getenv("GEMINI_MIN_STT_CONFIDENCE", "0.25"))
    if _looks_tamil_or_tanglish(clean):
        return False
    if conf is not None and conf < hard_min:
        return True
    return conf is not None and conf < soft_min and len(clean) < 8


def _looks_like_last_assistant(transcript: str, rows: list) -> bool:
    transcript_norm = _normalize_voice_text(transcript)
    if not transcript_norm:
        return True
    for row in reversed(rows or []):
        if row.get("speaker") != "assistant":
            continue
        assistant_text = row.get("message") or ""
        assistant_norm = _normalize_voice_text(assistant_text)
        if not assistant_norm:
            continue
        if transcript_norm == assistant_norm:
            return True
        similarity = SequenceMatcher(None, transcript_norm, assistant_norm).ratio()
        if similarity >= 0.82:
            print(f"[voice_respond] Discarding STT transcript similar to assistant audio similarity={similarity:.2f}")
            return True
        return False
    return False


def _deterministic_tamil_reply(text: str) -> Optional[str]:
    lower = (text or "").strip().lower()
    if not lower:
        return None

    yes_markers = ["ஆம்", "ஆமாம்", "சரி", "வேண்டும்", "ஓகே", "yes", "ok", "okay", "aam", "ama", "venum", "vendum"]
    no_markers = ["வேண்டாம்", "இல்லை", "no", "venam", "vendam"]
    reminder_markers = ["reminder", "ரிமைண்டர்", "நினைவூட்ட", "call", "அழைப்பு"]
    date_markers = ["நாளை", "திங்க", "செவ்வ", "புதன்", "வியாழ", "வெள்ளி", "சனி", "ஞாயிறு", "tomorrow", "monday"]
    identity_markers = [
        "யாரு", "யார்", "எங்கிருந்து", "எங்கேயிருந்து", "எங்கே இருந்து",
        "எதுக்கு", "ஏன் கால்", "எந்த company", "எந்த கம்பெனி",
        "why call", "who are", "where from",
    ]
    hearing_markers = ["ஹலோ", "hello", "கேக்குதா", "கேட்குதா", "பேசுறது கேக்குதா"]
    detail_markers = ["டீடைல் மட்டும்", "details only"]

    if any(m in lower for m in identity_markers):
        return "வணக்கம், நான் DigiDara Technologiesலிருந்து பேசுறேன். நீங்க AI course பற்றி enquire பண்ணிருந்தீங்க, அதுக்காகத்தான் கால் பண்ணேன்."
    if any(m in lower for m in hearing_markers):
        return "ஹலோ, கேட்குது. நான் DigiDara Technologiesலிருந்து பேசுறேன், இப்போ பேசலாமா?"
    if lower in detail_markers:
        return "நம்ம AI and Machine Learning courseல practical training, projects, internship support இருக்கும். நீங்க join பண்ண interestedஆ இருக்கீங்களா?"
    if len(lower.split()) <= 3 and any(m in lower for m in yes_markers):
        return "சரிங்க. AI course details கேக்கணுமா, இல்ல reminder call set பண்ணணுமா?"
    if len(lower.split()) <= 3 and any(m in lower for m in no_markers):
        return "சரி, பிரச்சனை இல்லை. வேற ஏதாவது details வேண்டும்னா சொல்லுங்க."

    if any(m in lower for m in reminder_markers) and any(m in lower for m in yes_markers):
        return "சரி, joining dateக்கு ஒரு நாள் முன்னாடி reminder call arrange பண்றோம். நன்றி, வணக்கம்."
    if any(m in lower for m in reminder_markers) and any(m in lower for m in no_markers):
        return "சரி, problem இல்ல. Joining dateல பார்க்கலாம், நன்றி."
    if any(m in lower for m in date_markers):
        return "சரி, அந்த date note பண்ணிக்கிறேன். Joining dateக்கு ஒரு நாள் முன்னாடி reminder call வேண்டுமா?"
    return None


def _tamil_cache_suffix(selected_lang: str) -> str:
    if selected_lang == "tamil":
        safe_voice = re.sub(r"[^a-zA-Z0-9_-]+", "", TAMIL_TTS_SPEAKER) or "voice"
        return f"_tamil_{safe_voice}"
    return f"_{selected_lang}"


TAMIL_FALLBACK_PHRASES = {
    "generic_greeting": "வணக்கம், டிஜிடாரா டெக்னாலஜி சார்பாக பேசுகிறேன்.",
    "inactivity_reprompt": "மன்னிக்கவும், எனக்கு சரியாக கேட்கவில்லை. மீண்டும் கூறவும்.",
    "inactivity_goodbye": "நன்றி, இந்த அழைப்பு இப்போது முடிவடைகிறது.",
    "stt_unavailable": "மன்னிக்கவும், எனது பேச்சு அங்கீகார சேவை தற்காலிகமாக கிடைக்கவில்லை.",
    "short_repeat": "மன்னிக்கவும், மீண்டும் கூறவும்.",
    "media_repeat": "மன்னிக்கவும், சரியாக கேட்கவில்லை. இன்னொரு முறை தெளிவாக சொல்ல முடியுமா?",
    "media_goodbye": "மன்னிக்கவும், இப்போது தெளிவாக கேட்கவில்லை. எங்கள் குழு உங்களை மீண்டும் தொடர்பு கொள்ளும். நன்றி.",
}
_TAMIL_FALLBACK_LOCK = threading.Lock()


def _tamil_fallback_filename(key: str) -> str:
    safe_voice = re.sub(r"[^a-zA-Z0-9_-]+", "", TAMIL_TTS_SPEAKER) or "voice"
    return f"tamil_fallback_{safe_voice}_{key}.wav"


def ensure_tamil_fallback_audio_cache() -> list[str]:
    """Pre-synthesize fixed Tamil fallback phrases once, outside live turns."""
    audio_dir = os.path.join(os.getcwd(), "audio_cache")
    os.makedirs(audio_dir, exist_ok=True)
    generated_or_existing = []

    with _TAMIL_FALLBACK_LOCK:
        for key, text in TAMIL_FALLBACK_PHRASES.items():
            filename = _tamil_fallback_filename(key)
            filepath = os.path.join(audio_dir, filename)
            generated_or_existing.append(filename)
            if os.path.exists(filepath):
                continue
            try:
                from app.services.gemini_service import text_to_speech
                audio_bytes = text_to_speech(
                    text,
                    language_code="ta-IN",
                    speaker=TAMIL_TTS_SPEAKER,
                )
                with open(filepath, "wb") as f:
                    f.write(audio_bytes)
                print(f"[TamilFallbackTTS] Cached {key}: {filename}")
            except Exception as e:
                print(f"[TamilFallbackTTS] Failed to cache {key}: {e}")
    return generated_or_existing


def _cached_tamil_audio_url(text: str, webhook_base: str) -> Optional[str]:
    for key, phrase in TAMIL_FALLBACK_PHRASES.items():
        if text == phrase:
            filename = _tamil_fallback_filename(key)
            filepath = os.path.join(os.getcwd(), "audio_cache", filename)
            if os.path.exists(filepath):
                return f"{webhook_base}/voice/audio/{filename}"
            print(
                f"[TamilFallbackTTS][WARNING] Missing cached Gemini WAV for '{key}'. "
                "Falling back to Twilio Google voice only as last resort."
            )
            return None
    return None


def _voice_xml(text: str, lang_code: str, webhook_base: Optional[str] = None) -> str:
    if lang_code == "ta-IN" and webhook_base:
        audio_url = _cached_tamil_audio_url(text, webhook_base)
        if audio_url:
            return f"<Play>{audio_url}</Play>"
        print(
            "[TamilFallbackTTS][WARNING] No cached Gemini fallback matched Tamil text. "
            "Using Twilio Google voice as last resort."
        )
    return get_say_xml(text, lang_code)


@router.get("/voice/audio/{filename}", tags=["Voice"])
def get_voice_audio(filename: str):
    audio_dir = os.path.join(os.getcwd(), "audio_cache")
    filepath = os.path.join(audio_dir, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio file not found")
    media_type = "audio/mpeg" if filename.endswith(".mp3") else "audio/wav"
    return FileResponse(filepath, media_type=media_type)

def resolve_hostname(hostname: str) -> str:
    """Resolves a hostname using local DNS, falling back to Google DoH if it fails."""
    import socket
    try:
        return socket.gethostbyname(hostname)
    except Exception:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        try:
            r = requests.get(f"https://8.8.8.8/resolve?name={hostname}", verify=False, timeout=5)
            if r.status_code == 200:
                data = r.json()
                if "Answer" in data:
                    for answer in data["Answer"]:
                        if answer.get("type") == 1:
                            return answer.get("data")
        except Exception as e:
            print(f"DoH resolution failed for {hostname}: {str(e)}")
    return hostname

def get_say_xml(text: str, lang_code: str) -> str:
    """Generates a <Say> tag with the appropriate Polly/Google voice for the language code to prevent Twilio schema crashes."""
    import html
    escaped_text = html.escape(text)
    voice = "Google.ta-IN-Standard-D" if lang_code == "ta-IN" else "Polly.Aditi"
    return f'<Say voice="{voice}" language="{lang_code}">{escaped_text}</Say>'


@router.post("/calls/start", dependencies=[Depends(current_admin)])
def start_call_without_customer_context(phone_number: str):
    raise HTTPException(
        status_code=400,
        detail=(
            "Use POST /calls/start/{customer_id}/{campaign_id}; provider calls require "
            "customer, campaign, language, and CRM context."
        ),
    )

@router.post(
    "/calls/start/{customer_id}/{campaign_id}",
    summary="Start outbound call for customer and campaign",
    description="Loads customer and campaign context, then places a provider-neutral outbound call.",
    dependencies=[Depends(current_admin)],
)
def start_outbound_call(
    customer_id: int,
    campaign_id: int,
    admin=Depends(current_admin),
    db: pymysql.Connection = Depends(get_db)
):
    organization_id = admin["organization_id"]
    customer = customer_service.get_customer_by_id(db, customer_id, organization_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer with ID {customer_id} not found."
        )

    campaign = campaign_service.get_campaign_by_id(db, campaign_id, organization_id)
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Campaign with ID {campaign_id} not found."
        )

    phone_number = customer.get("phone")
    if not phone_number:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Customer has no phone number registered."
        )

    # Clear conversation history and preserve language preference if already set
    cursor = db.cursor()
    cursor.execute("DELETE FROM conversations WHERE customer_id = %s", (customer_id,))
    cursor.execute(
        "SELECT language FROM customers WHERE id=%s AND organization_id=%s",
        (customer_id, organization_id),
    )
    cust = cursor.fetchone()
    if not cust or not cust.get("language"):
        cursor.execute(
            "UPDATE customers SET language=NULL WHERE id=%s AND organization_id=%s",
            (customer_id, organization_id),
        )
    db.commit()

    result = telephony_service.start_outbound_call(
        db, organization_id, customer_id, phone_number, campaign_id
    )
    return result


def _trigger_campaign_rows(
    db, organization_id: int, campaign_id: int, sheet_url: str, rows: list,
    write_status, write_feedback, source_label: str,
):
    """Shared candidate-selection/trigger core for both Google Sheets and
    file-upload bulk calling. write_status/write_feedback are the matching
    pair of functions for whichever source sheet_url refers to.
    """
    import re
    import threading

    if not rows:
        return {"message": f"No data rows found in {source_label}.", "calls_triggered": [], "sheet_url": sheet_url}

    triggerable_statuses = ["pending", "no-answer", "no answer", "no answered", "no-answered", "not answered", "not-answered", "queue", "queued", ""]
    triggerable_rows = []
    for row in rows:
        phone = row.get("phone")
        if not phone:
            continue
        clean_phone = re.sub(r"\D", "", phone)
        if not clean_phone:
            continue
        status_val = row.get("status") or ""
        clean_status = status_val.strip().lower()
        if clean_status in triggerable_statuses:
            triggerable_rows.append(row)

    if not triggerable_rows:
        return {"message": f"No pending or queueable data rows found in {source_label}.", "calls_triggered": [], "sheet_url": sheet_url}

    # Walk rows in order, resolving/creating the customer for each and
    # skipping anyone already on the do-not-call list, until a dialable row
    # is found. A suppressed row never places a call, so it must not become
    # the active row -- nothing would ever finalize it and the queue would
    # silently stall on it forever.
    active_row = None
    customer_id = None
    remaining_rows = []
    for candidate in triggerable_rows:
        if active_row is not None:
            remaining_rows.append(candidate)
            continue
        candidate_lang = candidate.get("language")
        if candidate_lang:
            candidate_lang = candidate_lang.strip().lower()
            if candidate_lang not in ["english", "tamil"]:
                candidate_lang = None
        candidate_id = customer_service.upsert_customer(
            db,
            organization_id=organization_id,
            name=(candidate.get("name") or "").strip() or "Customer",
            phone=candidate.get("phone"),
            language=candidate_lang,
            investigated_course=candidate.get("investigated_course"),
            internship_or_course=candidate.get("internship_or_course"),
            course_duration=candidate.get("course_duration"),
            sheet_url=sheet_url,
            sheet_row=int(candidate["row_number"]),
        )
        if telephony_service.is_suppressed(
            db, candidate_id, organization_id, candidate.get("phone")
        ):
            try:
                write_status(sheet_url, int(candidate["row_number"]), "do_not_call")
            except Exception as err:
                print(f"Failed to mark suppressed row {candidate['row_number']}: {err}")
            continue
        active_row = candidate
        customer_id = candidate_id

    if active_row is None:
        return {"message": "All queueable leads are on the do-not-call list.", "calls_triggered": [], "sheet_url": sheet_url}

    name = (active_row.get("name") or "").strip() or "Customer"
    phone = active_row.get("phone")
    queued_rows = remaining_rows

    def update_queue_statuses():
        for q_row in queued_rows:
            try:
                write_feedback(sheet_url, int(q_row["row_number"]), {"status": "queue"})
            except Exception as err:
                print(f"Failed to update queued status for row {q_row['row_number']}: {err}")

    threading.Thread(target=update_queue_statuses, daemon=True).start()

    cursor = db.cursor()
    cursor.execute("DELETE FROM conversations WHERE customer_id = %s", (customer_id,))
    db.commit()

    try:
        write_feedback(sheet_url, int(active_row["row_number"]), {"status": "ongoing"})
    except Exception as sheet_err:
        print(f"Failed to update active row status to ongoing: {sheet_err}")

    call_res = telephony_service.start_outbound_call(
        db,
        organization_id=organization_id,
        customer_id=customer_id,
        phone_number=phone,
        campaign_id=campaign_id,
        sheet_url=sheet_url,
        sheet_row=active_row["row_number"]
    )

    results = [{
        "name": name,
        "phone": phone,
        "row_number": active_row["row_number"],
        "call_sid": call_res.get("call_sid"),
        "status": call_res.get("status")
    }]

    if call_res.get("status") == "failed" and queued_rows:
        print("Active call failed to initiate. Triggering next queued call...")
        threading.Thread(
            target=telephony_service.trigger_next_queued_call,
            args=(sheet_url, campaign_id, organization_id),
            daemon=True
        ).start()

    return {
        "message": f"Successfully processed {source_label}. Triggered call for row {active_row['row_number']} and queued {len(queued_rows)} other call(s).",
        "calls_triggered": results,
        "sheet_url": sheet_url,
    }


@router.post(
    "/calls/run-sheet",
    summary="Trigger calls from Google Sheets data",
    description="Reads name, ph.no, and language from a Google Sheet, creates customers, and runs outbound calls.",
    dependencies=[Depends(current_admin)],
)
def run_sheet(
    request_data: SheetCallRequest,
    admin=Depends(current_admin),
    db: pymysql.Connection = Depends(get_db)
):
    organization_id = admin["organization_id"]
    campaign = campaign_service.get_campaign_by_id(
        db, request_data.campaign_id, organization_id
    )
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Campaign with ID {request_data.campaign_id} not found."
        )

    try:
        rows = google_sheets_service.read_sheet_data(request_data.sheet_url)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read sheet data: {str(e)}"
        )

    return _trigger_campaign_rows(
        db, organization_id, request_data.campaign_id, request_data.sheet_url, rows,
        google_sheets_service.update_sheet_status, google_sheets_service.update_sheet_feedback,
        "Google Sheet",
    )


@router.post(
    "/calls/run-upload",
    summary="Trigger calls from an uploaded Excel/CSV file",
    description="Parses an uploaded .csv or .xlsx lead list and runs the same "
    "campaign trigger flow as /calls/run-sheet, without needing Google Sheets access.",
    dependencies=[Depends(current_admin)],
)
async def run_upload(
    campaign_id: int = Form(...),
    file: UploadFile = File(...),
    admin=Depends(current_admin),
    db: pymysql.Connection = Depends(get_db),
):
    organization_id = admin["organization_id"]
    campaign = campaign_service.get_campaign_by_id(db, campaign_id, organization_id)
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Campaign with ID {campaign_id} not found."
        )

    content = await file.read()
    try:
        rows = bulk_upload_service.parse_file(file.filename or "", content)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if not rows:
        return {"message": "No data rows found in the uploaded file.", "calls_triggered": []}

    upload_reference = bulk_upload_service.create_batch(
        db, organization_id, campaign_id, file.filename or "upload", rows
    )
    stored_rows = bulk_upload_service.read_rows(upload_reference)

    return _trigger_campaign_rows(
        db, organization_id, campaign_id, upload_reference, stored_rows,
        bulk_upload_service.update_status, bulk_upload_service.update_feedback,
        "uploaded file",
    )


@router.get(
    "/calls/sheet-status",
    summary="Read current per-row status from a campaign Google Sheet",
    description="Re-reads the sheet's Name/Phone/Language/Status columns so the "
    "Bulk Calling UI can show which row is queued, ongoing, or done without "
    "the operator having to open the spreadsheet itself.",
    dependencies=[Depends(current_admin)],
)
def sheet_status(sheet_url: str):
    try:
        if bulk_upload_service.is_upload_reference(sheet_url):
            rows = bulk_upload_service.read_rows(sheet_url)
        else:
            rows = google_sheets_service.read_sheet_data(sheet_url)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read sheet data: {str(e)}",
        )
    return {
        "rows": [
            {
                "row_number": row.get("row_number"),
                "name": row.get("name") or "",
                "phone": row.get("phone") or "",
                "language": row.get("language") or "",
                "status": row.get("status") or "",
            }
            for row in rows
        ]
    }


@router.get(
    "/calls/logs",
    response_model=List[CallLogResponse],
    summary="Retrieve all call logs",
    description="Fetches a list of all call logs with pagination support.",
    dependencies=[Depends(current_admin)],
)
def read_call_logs(
    skip: int = 0,
    limit: int = 100,
    admin=Depends(current_admin),
    db: pymysql.Connection = Depends(get_db)
):
    # The Live Calls screen polls this endpoint. Reconcile only answered calls
    # that never established a media stream, using the provider CDR as the
    # terminal authority when Cloudflare also lost the hangup callback.
    try:
        from app.services.call_reconciliation_service import (
            reconcile_unstarted_provider_calls,
        )
        reconcile_unstarted_provider_calls(db, admin["organization_id"])
    except Exception as exc:
        print(f"[Call reconciliation] skipped: {type(exc).__name__}")
    return [
        with_call_guardrails(log)
        for log in call_log_service.get_all_call_logs(
            db, admin["organization_id"], skip=skip, limit=limit
        )
    ]

@router.get(
    "/calls/logs/{id}",
    response_model=CallLogResponse,
    summary="Retrieve a specific call log by ID",
    description="Fetches details of a specific call log by its database ID.",
    dependencies=[Depends(current_admin)],
)
def read_call_log(
    id: int,
    admin=Depends(current_admin),
    db: pymysql.Connection = Depends(get_db)
):
    log = call_log_service.get_call_log_by_id(db, id, admin["organization_id"])
    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Call log with ID {id} not found."
        )
    return with_call_guardrails(log)

@router.get(
    "/calls/logs/{id}/recording",
    summary="Securely proxy the provider recording",
    dependencies=[Depends(current_admin)],
)
def read_call_recording(
    id: int, enhanced: bool = True, admin=Depends(current_admin),
    db: pymysql.Connection = Depends(get_db),
):
    log = call_log_service.get_call_log_by_id(db, id, admin["organization_id"])
    recording_id = (log or {}).get("provider_recording_id") or (log or {}).get("recording_sid")
    if not log or not recording_id:
        raise HTTPException(status_code=404, detail="Recording is not available yet")
    try:
        audio, media_type = get_telephony_provider(db, admin["organization_id"]).get_recording(str(recording_id))
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Provider recording could not be retrieved: {type(exc).__name__}"
        ) from exc
    enhanced_applied = False
    if enhanced and shutil.which("ffmpeg"):
        # Phone audio is narrow-band by design. Denoise and normalize channels
        # independently so a quiet caller is raised without making the AI side clip.
        try:
            with tempfile.TemporaryDirectory(prefix="digidara-recording-") as tmp:
                source, output = Path(tmp) / "source.mp3", Path(tmp) / "enhanced.mp3"
                source.write_bytes(audio)
                result = subprocess.run([
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(source), "-filter_complex",
                    "[0:a]channelsplit=channel_layout=stereo[user][ai];"
                    "[user]highpass=f=120,lowpass=f=3600,afftdn=nr=16:nf=-45:tn=0,"
                    "dynaudnorm=f=120:g=11:p=0.80:m=12:r=0.14:n=0:c=1,"
                    "alimiter=limit=0.92[user_clean];"
                    "[ai]highpass=f=90,lowpass=f=3800,afftdn=nr=6:nf=-55:tn=0,"
                    "dynaudnorm=f=180:g=9:p=0.80:m=4:r=0.10:n=0:c=1,"
                    "alimiter=limit=0.92[ai_clean];"
                    "[user_clean][ai_clean]amerge=inputs=2[a]",
                    "-map", "[a]",
                    "-codec:a", "libmp3lame", "-b:a", "96k", str(output),
                ], capture_output=True, timeout=45, check=False)
                if result.returncode == 0 and output.exists() and output.stat().st_size:
                    audio = output.read_bytes()
                    enhanced_applied = True
                else:
                    print(f"[recording] FFmpeg enhancement failed: {result.stderr[-500:].decode(errors='ignore')}")
        except Exception as exc:
            print(f"[recording] Returning raw provider audio; enhancement error: {exc}")
    return Response(content=audio, media_type=media_type or "audio/mpeg", headers={
        "Content-Disposition": f"inline; filename=call-{id}.mp3",
        "Cache-Control": "private, max-age=300",
        "X-DigiDara-Audio-Enhanced": "true" if enhanced_applied else "false",
    })


@router.post(
    "/calls/logs/{id}/terminate",
    summary="Terminate an active provider call",
    dependencies=[Depends(current_admin)],
)
def terminate_call(
    id: int, admin=Depends(current_admin), db: pymysql.Connection = Depends(get_db),
):
    log = call_log_service.get_call_log_by_id(db, id, admin["organization_id"])
    if not log:
        raise HTTPException(status_code=404, detail="Call log not found")
    try:
        get_telephony_provider(db, admin["organization_id"]).terminate_call(
            call_id=log.get("provider_call_id"),
            request_id=log.get("provider_request_id"),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Provider could not terminate the call: {type(exc).__name__}"
        ) from exc
    call_log_service.update_call_log_status(
        db,
        log.get("provider_call_id") or log.get("provider_request_id") or log.get("call_sid"),
        "canceled",
    )
    return {"status": "canceled", "provider": log.get("provider") or "plivo"}


@router.api_route("/voice/welcome", methods=["GET", "HEAD", "POST"], tags=["Voice"])
async def voice_welcome(
    request: Request,
    campaign_id: int,
    customer_id: int,
    db: Optional[pymysql.Connection] = Depends(get_optional_db)
):
    # Historical Twilio answer route retained only to make rollback failures
    # explicit. Plivo uses /api/plivo/answer.
    return Response(
        content='<?xml version="1.0" encoding="UTF-8"?><Response><Hangup/></Response>',
        status_code=410,
        media_type="application/xml",
    )
    if request.method == "HEAD":
        return Response(content="", media_type="application/xml")

    # Log to workspace directory file for debugging
    try:
        import datetime
        project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        log_dir = os.path.join(project_dir, "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "voice_requests.log")
        form_data = {}
        if request.method == "POST":
            form_data = dict(await request.form())
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.datetime.now()}] /voice/welcome method={request.method} query={dict(request.query_params)} form={form_data}\n")
    except Exception as e:
        print("Failed to write voice welcome log:", str(e))

    # Load env base URL dynamically to ensure correct HTTPS reverse proxy mapping
    load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env")), override=True)
    webhook_base = os.getenv("WEBHOOK_BASE_URL")
    if webhook_base:
        webhook_base = webhook_base.strip().rstrip("/")
    else:
        webhook_base = str(request.base_url).rstrip("/")
    respond_url = f"{webhook_base}/voice/respond?campaign_id={campaign_id}&amp;customer_id={customer_id}"

    if db is None:
        return voice_error_response()

    # Always clear history for a new call
    try:
        cursor = db.cursor()
        cursor.execute("DELETE FROM conversations WHERE customer_id = %s", (customer_id,))
        cursor.execute("SELECT name, language FROM customers WHERE id = %s", (customer_id,))
        cust = cursor.fetchone()
        customer_name = (cust.get("name") or "").strip() if cust else "Customer"
        if not customer_name:
            customer_name = "Customer"
        selected_lang = cust.get("language") if cust else None
        if selected_lang:
            selected_lang = selected_lang.lower()

        # Default empty or invalid language to "english" and persist to DB
        if not selected_lang or selected_lang not in ["english", "tamil"]:
            selected_lang = "english"
            cursor.execute("UPDATE customers SET language = 'english' WHERE id = %s", (customer_id,))
        db.commit()
    except Exception as e:
        print(f"[voice_welcome] Failed to prepare call state: {e}")
        return voice_error_response()

    lang_code = "ta-IN" if selected_lang == "tamil" else "en-IN"
    suffix = _tamil_cache_suffix(selected_lang)
    filename = f"first_greeting_{customer_id}_{campaign_id}{suffix}.wav"
    audio_dir = os.path.join(os.getcwd(), "audio_cache")
    filepath = os.path.join(audio_dir, filename)
    # GPT-Realtime is the only active voice engine for both English and Tamil.
    # Do not branch on TWILIO_VOICE_ENGINE: stale .env values such as
    # `media_stream` previously sent calls into the legacy Gemini pipeline.
    stream_base = webhook_base.replace("https://", "wss://").replace("http://", "ws://")
    stream_ws_url = f"{stream_base}/openai-realtime/{customer_id}/{campaign_id}"
    print(
        f"[voice_welcome] OPENAI REALTIME ONLY | language={selected_lang} "
        f"customer={customer_id} campaign={campaign_id} url={stream_ws_url}"
    )
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{stream_ws_url}" />
    </Connect>
    <Hangup />
</Response>"""
    return Response(content=twiml, media_type="application/xml")

    # ── ENGLISH FAST PATH ────────────────────────────────────────────────────
    # ConversationRelay generates its greeting as TEXT over the WebSocket —
    # it does NOT need a pre-recorded WAV file. Waiting up to 2.5s here for a
    # WAV that will never be played was causing Twilio to time out and show
    # "an application error has occurred". For English, skip straight to
    # building the <ConversationRelay> TwiML — no polling, no WAV wait.
    if selected_lang == "english":
        relay_url = webhook_base.replace("https://", "wss://").replace("http://", "ws://")
        if voice_engine in {"relay", "conversationrelay", "conversation_relay"}:
            relay_ws_url = f"{relay_url}/conversation-relay/{customer_id}/{campaign_id}"
            relay_voice = os.getenv("TWILIO_RELAY_VOICE", "Polly.Aditi")

            twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <ConversationRelay url="{relay_ws_url}" voice="{relay_voice}" language="en-IN" welcomeGreeting="false" interruptible="true" />
    </Connect>
</Response>"""
            return Response(content=twiml, media_type="application/xml")

        ai_response = f"Hi {customer_name}, I'm calling from DigiDara Technologies. Is this a good time to talk?"
        try:
            save_conversation(db, customer_id, "assistant", ai_response)
        except Exception as e:
            print(f"[voice_welcome] Failed to save English greeting: {e}")

        say_xml = get_say_xml(ai_response, lang_code)
        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech" action="{respond_url}" method="POST" timeout="5" language="{lang_code}" speechTimeout="auto" speechModel="phone_call" bargeIn="true">
        {say_xml}
    </Gather>
    <Redirect method="POST">{respond_url}</Redirect>
</Response>"""
        return Response(content=twiml, media_type="application/xml")

    # ── TAMIL FALLBACK PATH ──────────────────────────────────────────────────
    # Tamil Gather fallback uses pre-recorded WAV greetings via Gemini TTS.
    if not os.path.exists(filepath):
        from app.services.twilio_service import pregenerate_first_greetings
        import threading
        try:
            threading.Thread(
                target=pregenerate_first_greetings,
                args=(customer_id, campaign_id, selected_lang),
                daemon=True
            ).start()
        except Exception as e:
            print("Failed to start pre-generation thread:", str(e))

        # Briefly poll for the file to appear. start_outbound_call already kicks
        # off pregeneration before Twilio reaches this endpoint, but if Twilio's
        # webhook arrives first (race condition), wait up to ~2.5s for the
        # background thread to finish writing the audio/text instead of
        # immediately falling back to a generic "Hello".
        import time as _time
        for _ in range(10):
            if os.path.exists(filepath):
                break
            _time.sleep(0.25)

    has_audio_file = os.path.exists(filepath)
    audio_url = f"{webhook_base}/voice/audio/{filename}"
    
    txt_filepath = os.path.join(audio_dir, f"first_greeting_{customer_id}_{campaign_id}{suffix}.txt")
    try:
        with open(txt_filepath, "r", encoding="utf-8") as f:
            ai_response = f.read().strip()
    except Exception:
        ai_response = "Hello"
        
    cursor = db.cursor()
    cursor.execute(
        "SELECT count(*) as count FROM conversations WHERE customer_id = %s",
        (customer_id,)
    )
    count_row = cursor.fetchone()
    if not count_row or count_row.get("count", 0) == 0:
        customer_message = "நான் தமிழைத் தேர்ந்தெடுத்துள்ளேன். தயவுசெய்து உரையாடலைத் தொடங்கவும்."
        save_conversation(db, customer_id, "user", customer_message)
        save_conversation(db, customer_id, "assistant", ai_response)

    # Tamil only reaches here — English already returned via the fast path above.
    if has_audio_file:
        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech" action="{respond_url}" method="POST" timeout="5" language="{lang_code}" speechTimeout="auto" speechModel="phone_call" bargeIn="true">
        <Play>{audio_url}</Play>
    </Gather>
    <Redirect method="POST">{respond_url}</Redirect>
</Response>"""
    else:
        ai_response = TAMIL_FALLBACK_PHRASES["generic_greeting"]
        say_xml = _voice_xml(ai_response, lang_code, webhook_base)
        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech" action="{respond_url}" method="POST" timeout="5" language="{lang_code}" speechTimeout="auto" speechModel="phone_call" bargeIn="true">
        {say_xml}
    </Gather>
    <Redirect method="POST">{respond_url}</Redirect>
</Response>"""
    return Response(content=twiml, media_type="application/xml")



@router.api_route("/voice/respond", methods=["GET", "POST"], tags=["Voice"])
async def voice_respond(
    request: Request,
    campaign_id: int,
    customer_id: int,
    db: Optional[pymysql.Connection] = Depends(get_optional_db)
):
    return Response(
        content='<?xml version="1.0" encoding="UTF-8"?><Response><Hangup/></Response>',
        status_code=410,
        media_type="application/xml",
    )
    if request.method == "HEAD":
        return Response(content="", media_type="application/xml")

    form_data = {}
    if request.method == "POST":
        form_data = dict(await request.form())
        speech_result = form_data.get("SpeechResult")
        recording_url = form_data.get("RecordingUrl") or form_data.get("recording_url")
    else:
        speech_result = request.query_params.get("SpeechResult")
        recording_url = request.query_params.get("RecordingUrl") or request.query_params.get("recording_url")

    # Log to workspace directory file for debugging
    try:
        import datetime
        project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        log_dir = os.path.join(project_dir, "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "voice_requests.log")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.datetime.now()}] /voice/respond method={request.method} query={dict(request.query_params)} form={form_data}\n")
    except Exception as e:
        print("Failed to write voice respond log:", str(e))
        
    # Load env base URL dynamically to ensure correct HTTPS reverse proxy mapping
    load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env")), override=True)
    webhook_base = os.getenv("WEBHOOK_BASE_URL")
    if webhook_base:
        webhook_base = webhook_base.rstrip("/")
    else:
        webhook_base = str(request.base_url).rstrip("/")
    respond_url = f"{webhook_base}/voice/respond?campaign_id={campaign_id}&amp;customer_id={customer_id}"

    if db is None:
        return voice_error_response()

    # Retrieve customer's preferred language from the database
    try:
        cursor = db.cursor()
        cursor.execute("SELECT language FROM customers WHERE id = %s", (customer_id,))
        cust = cursor.fetchone()
        selected_lang = cust.get("language") if cust else None
        if selected_lang:
            selected_lang = selected_lang.lower()
    except Exception as e:
        print(f"[voice_respond] Failed to load customer language: {e}")
        return voice_error_response()

    async def handle_inactivity():
        is_tamil = (selected_lang == "tamil")
        reprompt_text = "மன்னிக்கவும், எனக்கு சரியாக கேட்கவில்லை. மீண்டும் கூறவும்." if is_tamil else "I'm sorry, I didn't catch that. Could you please repeat?"
        goodbye_text = "நன்றி, இந்த அழைப்பு இப்போது முடிவடைகிறது." if is_tamil else "Thank you, this call is now ending due to inactivity."
        lang_code = "ta-IN" if is_tamil else "en-IN"
        
        # Check if the last assistant message was a silence reprompt
        cursor = db.cursor()
        cursor.execute(
            "SELECT speaker, message FROM conversations WHERE customer_id = %s ORDER BY id DESC LIMIT 1",
            (customer_id,)
        )
        last_msg = cursor.fetchone()
        
        if last_msg and last_msg.get("speaker") == "assistant" and last_msg.get("message") == reprompt_text:
            text_to_say = goodbye_text
            should_hangup = True
        else:
            text_to_say = reprompt_text
            should_hangup = False
            from app.services.conversation_service import save_conversation
            save_conversation(db, customer_id, "assistant", reprompt_text)
            
        audio_url = None
        if selected_lang == "tamil":
            audio_url = _cached_tamil_audio_url(text_to_say, webhook_base)
        else:
            from app.services.elevenlabs_service import text_to_speech_elevenlabs_async as _welcome_tts
            try:
                audio_bytes = await _welcome_tts(text_to_say)
                filename = f"goodbye_timeout_{uuid.uuid4().hex[:8]}.wav"
                audio_dir = os.path.join(os.getcwd(), "audio_cache")
                os.makedirs(audio_dir, exist_ok=True)
                with open(os.path.join(audio_dir, filename), "wb") as f:
                    f.write(audio_bytes)
                audio_url = f"{webhook_base}/voice/audio/{filename}"
            except Exception as e:
                print("Error TTS Generation failed:", str(e))

        if should_hangup:
            if audio_url:
                twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Play>{audio_url}</Play>
    <Hangup />
</Response>"""
            else:
                say_xml = _voice_xml(text_to_say, lang_code, webhook_base)
                twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    {say_xml}
    <Hangup />
</Response>"""
        else:
            if audio_url:
                twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech" action="{respond_url}" method="POST" timeout="5" language="{lang_code}" speechTimeout="auto" speechModel="phone_call" bargeIn="true">
        <Play>{audio_url}</Play>
    </Gather>
    <Redirect method="POST">{respond_url}</Redirect>
</Response>"""
            else:
                say_xml = _voice_xml(text_to_say, lang_code, webhook_base)
                twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech" action="{respond_url}" method="POST" timeout="5" language="{lang_code}" speechTimeout="auto" speechModel="phone_call" bargeIn="true">
        {say_xml}
    </Gather>
    <Redirect method="POST">{respond_url}</Redirect>
</Response>"""
        return Response(content=twiml, media_type="application/xml")

    cursor.execute(
        "SELECT speaker, message FROM conversations WHERE customer_id = %s ORDER BY id ASC",
        (customer_id,)
    )
    rows = cursor.fetchall()

    # Handle case where user said nothing/empty recording (Hang up due to inactivity)
    if not recording_url and not speech_result:
        return await handle_inactivity()
        
    audio_bytes = None
    if speech_result and recording_url:
        print("[voice_respond] SpeechResult present; skipping RecordingUrl download.")
        recording_url = None

    if not speech_result and recording_url:
        recording_duration = (
            form_data.get("RecordingDuration")
            or form_data.get("RecordingDurationMs")
            or request.query_params.get("RecordingDuration")
            or request.query_params.get("RecordingDurationMs")
        )
        try:
            duration_value = float(recording_duration) if recording_duration not in (None, "") else None
        except (TypeError, ValueError):
            duration_value = None
        if duration_value is not None and duration_value <= 0:
            print("[voice_respond] RecordingUrl duration is zero; treating as inactivity.")
            return await handle_inactivity()

        # Ensure URL ends with .wav for raw audio download
        audio_url = recording_url
        if not audio_url.endswith(".wav"):
            audio_url = f"{audio_url}.wav"

        # Download the audio file using Twilio authentication
        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        auth = (account_sid, auth_token) if (account_sid and auth_token) else None

        # No DNS hack needed — just use the URL directly with proper auth
        def fetch_audio():
            return requests.get(
                audio_url,
                auth=auth,
                timeout=10
            )

        try:
            audio_response = await asyncio.to_thread(fetch_audio)
            if audio_response.status_code != 200:
                print(f"Twilio download failed with status {audio_response.status_code}: {audio_response.text}")
                err_msg = "மன்னிக்கவும், எனக்கு சரியாக கேட்கவில்லை. மீண்டும் கூறவும்." if selected_lang == "tamil" else "I am having trouble hearing you. Could you repeat?"
                lang_code = "ta-IN" if selected_lang == "tamil" else "en-IN"
                say_xml = _voice_xml(err_msg, lang_code, webhook_base)
                twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    {say_xml}
    <Gather input="speech" action="{respond_url}" method="POST" timeout="5" language="{lang_code}" speechTimeout="auto" speechModel="phone_call" bargeIn="true" />
</Response>"""
                return Response(content=twiml, media_type="application/xml")
            audio_bytes = audio_response.content
        except Exception as e:
            print("Download Error:", str(e))
            err_msg = "மன்னிக்கவும், எனக்கு சரியாக கேட்கவில்லை. மீண்டும் கூறவும்." if selected_lang == "tamil" else "I had a network issue hearing you. Could you repeat?"
            lang_code = "ta-IN" if selected_lang == "tamil" else "en-IN"
            say_xml = _voice_xml(err_msg, lang_code, webhook_base)
            twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    {say_xml}
    <Gather input="speech" action="{respond_url}" method="POST" timeout="5" language="{lang_code}" speechTimeout="auto" speechModel="phone_call" bargeIn="true" />
</Response>"""
            return Response(content=twiml, media_type="application/xml")

    # If language preference is not yet set, we perform language selection detection!
    if not selected_lang:
        if speech_result:
            selected_lang = "english"
            customer_message = speech_result
        else:
            from app.services.gemini_service import speech_to_text_async
            try:
                message_en = await speech_to_text_async(audio_bytes, filename="recording.wav", language_code="en-IN")
            except Exception:
                message_en = ""
                
            if "english" in message_en.lower():
                selected_lang = "english"
                customer_message = "English"
            else:
                try:
                    message_ta = await speech_to_text_async(audio_bytes, filename="recording.wav", language_code="ta-IN")
                except Exception:
                    message_ta = ""
                    
                if "தமிழ்" in message_ta or "tamil" in message_ta.lower() or "tamil" in message_en.lower():
                    selected_lang = "tamil"
                    customer_message = "தமிழ்"
                else:
                    # Fallback based on content length
                    if len(message_ta.strip()) > len(message_en.strip()):
                        selected_lang = "tamil"
                        customer_message = message_ta if message_ta.strip() else "தமிழ்"
                    else:
                        selected_lang = "english"
                        customer_message = message_en if message_en.strip() else "English"
                        
        # Update database language preference
        cursor.execute("UPDATE customers SET language = %s WHERE id = %s", (selected_lang, customer_id))
        db.commit()
    else:
        # Transcribe based on saved language preference
        lang_code = "ta-IN" if selected_lang == "tamil" else "en-IN"
        if speech_result:
            customer_message = speech_result
        else:
            from app.services.gemini_service import speech_to_text_async
            try:
                customer_message = await speech_to_text_async(audio_bytes, filename="recording.wav", language_code=lang_code)
            except Exception as e:
                print("STT Error:", str(e))
                err_msg = "மன்னிக்கவும், எனது பேச்சு அங்கீகார சேவை தற்காலிகமாக கிடைக்கவில்லை." if selected_lang == "tamil" else "I am sorry, my speech recognition service is temporarily unavailable."
                say_xml = _voice_xml(err_msg, lang_code, webhook_base)
                twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    {say_xml}
    <Hangup />
</Response>"""
                return Response(content=twiml, media_type="application/xml")
        
    if not customer_message.strip():
        return await handle_inactivity()
    if _looks_like_last_assistant(customer_message, rows):
        print("[voice_respond] STT matched last assistant message; treating as empty customer input.")
        return await handle_inactivity()

    from app.services.conversation_service import save_conversation
    try:
        save_conversation(db, customer_id, "user", customer_message)
    except Exception as save_err:
        print(f"[voice_respond] Failed to save user conversation: {save_err}")
        
    # Fetch conversation history from the database
    history = []
    for row in rows:
        role = "assistant" if row["speaker"] == "assistant" else "user"
        history.append({"role": role, "content": row["message"]})

    # Retrieve customer details
    cursor.execute("SELECT name, investigated_course, internship_or_course, course_duration FROM customers WHERE id = %s", (customer_id,))
    cust_row = cursor.fetchone()
    customer_name = (cust_row.get("name") or "").strip() if cust_row else "Customer"
    if not customer_name:
        customer_name = "Customer"
    investigated_course = cust_row.get("investigated_course") if cust_row else None
    internship_or_course = cust_row.get("internship_or_course") if cust_row else None
    course_duration = cust_row.get("course_duration") if cust_row else None

    # Retrieve campaign prompt
    campaign = campaign_service.get_campaign_by_id(db, campaign_id)
    prompt = campaign.get("ai_prompt") if campaign else "You are a helpful assistant."
    
    # Format placeholders in prompt if present
    for placeholder, value in [
        ("{customer_name}", customer_name),
        ("{name}", customer_name),
        ("{customer_language}", selected_lang or "english"),
        ("{language}", selected_lang or "english")
    ]:
        if placeholder in prompt:
            prompt = prompt.replace(placeholder, str(value))

    # Conversation context — supplements the campaign prompt without overriding it
    if investigated_course:
        internship_or_course_str = internship_or_course or "course/internship"
        duration_str = f" of duration {course_duration}" if course_duration else ""
        counseling_instructions = (
            f"\n\nCONVERSATION CONTEXT:\n"
            f"- You are speaking with {customer_name} from DigiDara Technologies.\n"
            f"- They enquired about {internship_or_course_str} in {investigated_course}{duration_str}.\n"
            f"- Follow the campaign instructions above. Help them confirm joining date or answer their questions.\n"
        )
    else:
        counseling_instructions = (
            f"\n\nCONVERSATION CONTEXT:\n"
            f"- You are speaking with {customer_name} from DigiDara Technologies.\n"
            f"- Follow the campaign instructions above to guide this conversation.\n"
        )
    counseling_instructions += (
        "\nFLOW RULES:\n"
        "- If they want to join: confirm their preferred date, then ask if they want a reminder call one day before.\n"
        "- If they say yes to reminder: note it warmly and close the call.\n"
        "- If they say no to reminder: acknowledge politely and close the call.\n"
        "- If they want a callback: ask what date/time suits them.\n"
        "- If they ask about courses, services, fees, or DigiDara: answer naturally from your knowledge.\n"
        "- Never mention internal tools, emails, staff names, or system operations.\n"
    )
    prompt += counseling_instructions

            
    # Inject language constraints into LLM prompt
    if selected_lang == "tamil":
        # Override counseling instructions with Tamil versions so LLM never outputs English
        # Keep the campaign prompt already built — do NOT reset it here
        for placeholder, value in [
            ("{customer_name}", customer_name),
            ("{name}", customer_name),
            ("{customer_language}", "tamil"),
            ("{language}", "tamil")
        ]:
            if placeholder in prompt:
                prompt = prompt.replace(placeholder, str(value))

        if investigated_course:
            internship_or_course_str = internship_or_course or "பயிற்சி"
            duration_str = f" ({course_duration})" if course_duration else ""
            step2_script = f"நீங்க {investigated_course} {internship_or_course_str}{duration_str} பத்தி விசாரிச்சிருந்தீங்க. எந்த தேதியில ஜாயின் பண்ணலாம்னு பிளான் பண்ணிருக்கீங்க?"
        else:
            step2_script = "எந்த தேதியில ஜாயின் பண்ணலாம்னு பிளான் பண்ணிருக்கீங்க?"

        tamil_strict_prompt = (
            f"\n\nதமிழ் உரையாடல் கட்டுப்பாடுகள் (இதை கண்டிப்பாக பின்பற்றவும்):\n"
            f"\nநீங்கள் டிஜிடாரா டெக்னாலஜி சார்பாக அழைக்கும் ஒரு நட்பான AI assistant. "
            f"வணக்கம் சொல்லி campaign prompt-ல் உள்ளதை ஏற்கனவே சொல்லிவிட்டோம். "
            f"இப்போது customer பதில் சொல்கிறார் — அதற்கு இயற்கையாக respond பண்ணுங்கள்.\n"
            f"\nGOAL: {step2_script}\n"
            f"\nFLOW:\n"
            f"- Customer ஒரு தேதி சொன்னால்: confirm பண்ணுங்க, பிறகு கேளுங்க: 'ஜாயின் பண்றதுக்கு ஒரு நாள் முன்னாடி ரிமைண்டர் கால் வேணுமா?'\n"
            f"- Reminder YES: 'சரிங்க, ரிமைண்டர் கால் அரேஞ்ச் பண்றோம். ரொம்ப நன்றி, வணக்கம்.' (close)\n"
            f"- Reminder NO: 'சரிங்க, அன்னைக்கு பார்க்கலாம். ரொம்ப நன்றி, வணக்கம்.' (close)\n"
            f"- Delay/callback: 'சரிங்க, எப்போ திரும்ப கால் பண்ணலாம்?'\n"
            f"- Customer கேள்வி கேட்டால் (course, fee, etc.): campaign prompt + knowledge base-ல் இருந்து இயற்கையாக பதில் சொல்லுங்கள்.\n"
            f"\nRULES:\n"
            f"1. Response 1-3 sentences மட்டும். நீண்ட பதில் வேண்டாம்.\n"
            f"2. பேச்சு வழக்கு தமிழ் மட்டும் — textbook/formal/எழுத்துவழக்கு தமிழ் வேண்டாம்.\n"
            f"3. சென்னை, கோயம்புத்தூர், மதுரை, திருச்சி callers புரிஞ்சுக்கிற மாதிரி simple spoken Tamil use பண்ணுங்கள்.\n"
            f"4. Natural Tanglish okay: course, internship, WhatsApp, date, sure, okay, reminder call மாதிரி daily words use பண்ணலாம்.\n"
            f"5. Sanskritized/formal words avoid பண்ணுங்கள்; human phone agent மாதிரி casual-ஆ பேசுங்கள்.\n"
            f"6. Markdown formatting வேண்டாம்.\n"
            f"7. Internal tool names, email, staff names சொல்லாதீங்க.\n"
        )
        prompt += tamil_strict_prompt
        prompt += (
            "\n\nTamil STT handling rule: If the customer transcript contains Tamil or Tanglish words, "
            "treat it as valid and answer directly in Tamil. Do not say you cannot understand unless "
            "the transcript is empty or meaningless. If the customer says they want a reminder call, "
            "confirm the reminder and close politely.\n"
        )
    else:
        prompt += (
            "\n\nIMPORTANT STYLE RULES:\n"
            "- Speak like a warm, real DigiDara team member on a phone call.\n"
            "- MAXIMUM 2 sentences per reply — be concise and human.\n"
            "- If the customer says they are busy, in a hurry, or has work: immediately give a ONE sentence summary and ask one simple closing question.\n"
            "- If they say quickly summarize or in short: give a single punchy sentence, nothing more.\n"
            "- No markdown. No lists. Plain spoken words only.\n"
            "- If you don't have specific details (like pricing): one sentence offer to call back.\n"
        )
    
    # ── FAST PATH: Async LLM streaming + concurrent TTS pipeline ─────────────
    # Key insight for the Gather/Respond flow:
    # The full reply must exist before we can return TwiML, BUT we can still
    # use AsyncGroq streaming to start generating immediately (lower TTFT) and
    # run TTS concurrently on the first complete sentence while the LLM is
    # still generating the rest.  We save whichever audio is ready first.
    #
    # Timing improvement vs old asyncio.to_thread approach:
    #   Old: wait full LLM response → wait full TTS → return TwiML   (~2.5-4s)
    #   New: stream LLM → sentence 1 TTS starts immediately → return  (~1.5-2.5s)

    # Fast RAG: only retrieve if the customer is asking a knowledge question
    # (not just confirming a date or saying yes/no) — avoids ChromaDB latency
    # on simple turns like "Yes", "Next Monday", "Okay".
    use_rag = os.getenv("VOICE_USE_RAG", "false").strip().lower() in {"1", "true", "yes", "on"}
    from app.services.groq_service import needs_rag
    if use_rag and needs_rag(customer_message or ""):
        try:
            if selected_lang == "tamil":
                from app.livekit_agent.memory_kb import search as kb_search
                context = kb_search(customer_message, lang="ta", top_k=3)
                if context:
                    prompt += f"\n\nRETRIEVED KNOWLEDGE:\n{context}"
            else:
                from app.services import rag_service
                if rag_service.is_available():
                    chunks = rag_service.retrieve(customer_message, top_k=3)
                    if chunks:
                        context = rag_service.build_context_block(chunks)
                        prompt += f"\n\n{context}"
        except Exception as rag_err:
            print(f"[voice_respond] RAG lookup failed: {rag_err}")

    lang_code = "ta-IN" if selected_lang == "tamil" else "en-IN"
    audio_dir = os.path.join(os.getcwd(), "audio_cache")
    os.makedirs(audio_dir, exist_ok=True)

    reply = _deterministic_tamil_reply(customer_message) if selected_lang == "tamil" else ""
    audio_url = None
    use_external_tts = (
        selected_lang == "tamil"
        or os.getenv("VOICE_USE_EXTERNAL_TTS", "false").strip().lower() in {"1", "true", "yes", "on"}
    )
    # English → ElevenLabs
    # Tamil → Gemini
    if selected_lang == "tamil":
        from app.services.gemini_service import text_to_speech_async as _tts_fn
    else:
        from app.services.elevenlabs_service import text_to_speech_elevenlabs_async as _tts_fn

    async def text_to_speech_async(text: str, language_code: str = "en-IN") -> bytes:
        if selected_lang == "tamil":
            return await _tts_fn(text, language_code=language_code, speaker=TAMIL_TTS_SPEAKER)
        return await _tts_fn(text)

    from app.services.groq_service import get_cached_response, set_cached_response, generate_response_voice

    # ── Fast path: cache hit for simple turns (yes/ok/sure/dates) ─────────
    cached_reply = get_cached_response(prompt, customer_message) if not reply else None
    if cached_reply:
        reply = cached_reply
        if use_external_tts:
            try:
                audio_bytes = await asyncio.wait_for(text_to_speech_async(reply, language_code=lang_code), timeout=6.0)
                fname = f"respond_{uuid.uuid4().hex[:8]}.wav"
                with open(os.path.join(audio_dir, fname), "wb") as f:
                    f.write(audio_bytes)
                audio_url = f"{webhook_base}/voice/audio/{fname}"
            except Exception as tts_err:
                print(f"[voice_respond] Cache TTS error: {tts_err}")
    elif not reply:
        # ── Main path: smart RAG routing + AsyncGroq + TTS ────────────────
        # generate_response_voice() decides internally whether to call RAG
        # based on the customer message — knowledge questions get RAG,
        # simple turns (yes/ok/dates) skip it entirely saving ~150ms.
        try:
            reply = await asyncio.wait_for(
                generate_response_voice(prompt, customer_message, history, language=selected_lang),
                timeout=8.0,
            )
            reply = (reply or "").strip()

            # Cache for future identical short turns
            set_cached_response(prompt, customer_message, reply)

            if reply and use_external_tts:
                audio_bytes = await asyncio.wait_for(text_to_speech_async(reply, language_code=lang_code), timeout=6.0)
                fname = f"respond_{uuid.uuid4().hex[:8]}.wav"
                with open(os.path.join(audio_dir, fname), "wb") as f:
                    f.write(audio_bytes)
                audio_url = f"{webhook_base}/voice/audio/{fname}"

        except Exception as llm_err:
            print(f"[voice_respond] LLM/TTS error: {llm_err}")
            try:
                from app.services.groq_service import generate_response
                reply = await asyncio.wait_for(
                    asyncio.to_thread(generate_response, prompt, customer_message, history, selected_lang),
                    timeout=6.0,
                )
                reply = (reply or "").strip()
                if reply and use_external_tts:
                    audio_bytes = await asyncio.wait_for(text_to_speech_async(reply, language_code=lang_code), timeout=6.0)
                    fname = f"respond_{uuid.uuid4().hex[:8]}.wav"
                    with open(os.path.join(audio_dir, fname), "wb") as f:
                        f.write(audio_bytes)
                    audio_url = f"{webhook_base}/voice/audio/{fname}"
            except Exception as fb_err:
                print(f"[voice_respond] Fallback also failed: {fb_err}")

    if not reply:
        reply = "I'm sorry, I didn't catch that. Could you please repeat?" if selected_lang != "tamil" else "மன்னிக்கவும், மீண்டும் கூறவும்."

    # Save assistant message to database. User turn is saved before LLM generation
    # so turn order stays stable even if another webhook arrives late.
    try:
        save_conversation(db, customer_id, "assistant", reply)
    except Exception as save_err:
        print(f"[voice_respond] Failed to save conversation: {save_err}")

    # Detect goodbye
    is_goodbye = any(word in reply.lower() for word in [
        "goodbye", "bye", "take care", "have a nice day", "have a great day",
        "ரொம்ப நன்றி, வணக்கம்", "நன்றி, வணக்கம்", "போய் வருகிறேன்",
        "மிக்க நன்றி", "நாளை பார்க்கலாம்", "விரைவில் பார்க்கலாம்",
    ])

    if is_goodbye:
        if audio_url:
            twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Play>{audio_url}</Play>
    <Hangup />
</Response>"""
        else:
            say_xml = _voice_xml(reply, lang_code, webhook_base)
            twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    {say_xml}
    <Hangup />
</Response>"""
    else:
        if audio_url:
            twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech" action="{respond_url}" method="POST" timeout="5" language="{lang_code}" speechTimeout="auto" speechModel="phone_call" bargeIn="true">
        <Play>{audio_url}</Play>
    </Gather>
    <Redirect method="POST">{respond_url}</Redirect>
</Response>"""
        else:
            say_xml = _voice_xml(reply, lang_code, webhook_base)
            twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech" action="{respond_url}" method="POST" timeout="5" language="{lang_code}" speechTimeout="auto" speechModel="phone_call" bargeIn="true">
        {say_xml}
    </Gather>
    <Redirect method="POST">{respond_url}</Redirect>
</Response>"""
        
    return Response(content=twiml, media_type="application/xml")


@router.websocket("/media-stream/{customer_id}/{campaign_id}")
async def media_stream(
    websocket: WebSocket,
    customer_id: int,
    campaign_id: int,
):
    await websocket.accept()
    # Disabled permanently: this legacy endpoint uses Gemini/Sarvam/ElevenLabs.
    # All new calls connect to /ws/plivo/media via /api/plivo/answer.
    print(
        f"[LEGACY MEDIA STREAM BLOCKED] customer={customer_id} campaign={campaign_id}. "
        "Restart the backend and place a new call through the Plivo answer route."
    )
    await websocket.close(code=1008, reason="Legacy media stream disabled; use OpenAI Realtime")
    return

    print(f"WebSocket connection accepted for customer {customer_id}, campaign {campaign_id}")
    
    # Open database connection
    db = get_db_connection()
    cursor = db.cursor()
    
    # Fetch customer details
    cursor.execute("SELECT name, language, investigated_course, internship_or_course, course_duration FROM customers WHERE id = %s", (customer_id,))
    cust = cursor.fetchone()
    customer_name = cust["name"] if cust else "Customer"
    selected_lang = cust["language"] if (cust and cust.get("language")) else "english"
    selected_lang = selected_lang.lower()
    if selected_lang == "tamil":
        print(f"[media_stream] Tamil call on wrong handler, closing WebSocket. customer={customer_id}")
        db.close()
        await websocket.close()
        return
    
    investigated_course = cust.get("investigated_course") if cust else None
    internship_or_course = cust.get("internship_or_course") if cust else None
    course_duration = cust.get("course_duration") if cust else None
    
    lang_code = "ta-IN" if selected_lang == "tamil" else "en-IN"
    
    # Retrieve campaign prompt
    campaign = campaign_service.get_campaign_by_id(db, campaign_id)
    base_prompt = campaign.get("ai_prompt") if campaign else "You are a helpful assistant."
    
    # Format placeholders in prompt
    for placeholder, value in [
        ("{customer_name}", customer_name),
        ("{name}", customer_name),
        ("{customer_language}", selected_lang),
        ("{language}", selected_lang)
    ]:
        if placeholder in base_prompt:
            base_prompt = base_prompt.replace(placeholder, str(value))

    if selected_lang == "tamil" and len(base_prompt) > 1800:
        base_prompt = base_prompt[:1800] + "\n\n[Campaign prompt shortened for live Tamil call latency.]"
            
    # Inject language + human conversation rules
    if selected_lang == "tamil":
        base_prompt += (
            "\n\nIMPORTANT LANGUAGE & STYLE RULES:\n"
            "- Speak like a natural Tamil-speaking phone agent from Tamil Nadu.\n"
            "- Use casual spoken Tamil (பேச்சுவழக்கு), not literary/formal Tamil (எழுத்துவழக்கு).\n"
            "- Use common everyday words a caller from Chennai, Coimbatore, Madurai, or Trichy would understand.\n"
            "- Avoid Sanskritized or textbook Tamil words when a simple spoken word is more natural.\n"
            "- Natural Tanglish code-switching is allowed for common words like course, internship, WhatsApp, date, sure, okay, reminder call.\n"
            "- Keep Tamil script for Tamil words; English loanwords may stay natural when callers commonly use them.\n"
            "- Sound like a warm, friendly human advisor on a phone call.\n"
            "- MAXIMUM 2 sentences per reply. If customer is busy or says quickly summarize: ONE sentence only.\n"
            "- No markdown formatting (no **, no bullet points, no lists, no headers). Plain spoken text only.\n"
            "- If you don't know something, say so naturally and offer to have someone call back.\n"
            "- Never say 'I am an AI' or reveal you are a bot. You are a DigiDara team member.\n"
            "- If the customer transcript contains Tamil or Tanglish words, treat it as valid and answer directly. Do not ask them to repeat unless the transcript is empty or meaningless.\n"
            "- If the customer says they want a reminder call, confirm the reminder call and close politely.\n"
        )
    else:
        base_prompt += (
            "\n\nIMPORTANT LANGUAGE & STYLE RULES:\n"
            "- Speak and respond in natural, friendly English — like a real person on a phone call.\n"
            "- MAXIMUM 2 sentences per reply. If customer is busy or says quickly summarize: ONE sentence only.\n"
            "- No markdown formatting (no **, no bullet points, no lists, no headers). Plain spoken text only.\n"
            "- Sound warm and helpful, not robotic. Use natural transitions like 'Sure!', 'Absolutely', 'Great question'.\n"
            "- If you don't know something, say so honestly and offer to have someone call back.\n"
            "- Never say 'I am an AI' or reveal you are a bot. You are a DigiDara team member.\n"
        )

    # Conversation context — supplements campaign prompt, never overrides it
    if investigated_course:
        internship_or_course_str = internship_or_course or "course/internship"
        duration_str = f" of duration {course_duration}" if course_duration else ""
        counseling_instructions = (
            f"\n\nCONVERSATION CONTEXT:\n"
            f"- You are speaking live with {customer_name} from DigiDara Technologies.\n"
            f"- They enquired about {internship_or_course_str} in {investigated_course}{duration_str}.\n"
            f"- The greeting has already been spoken. Now respond to what they say next.\n"
            f"- Follow the campaign instructions above. Answer questions honestly, help confirm joining date.\n"
        )
    else:
        counseling_instructions = (
            f"\n\nCONVERSATION CONTEXT:\n"
            f"- You are speaking live with {customer_name} from DigiDara Technologies.\n"
            f"- The greeting has already been spoken. Respond naturally to what they say.\n"
            f"- Follow the campaign instructions above.\n"
        )
    
    # Flow rules:
    counseling_instructions += (
        "\nCONVERSATIONAL FLOW RULES (Act like a professional human advisor):\n"
        "- NEVER mention any internal tools, database operations, or functions (e.g., do not say 'I am calling a tool' or 'updating the database'). Speak 100% naturally.\n"
        "- NEVER mention the word 'application', 'system', 'error', 'bug', 'crash', or any internal failure. If the caller mentions a software issue, politely steer the call back to the enquiry.\n"
        "- NEVER mention email, email confirmation, or sending any kind of message. No emails are sent from our side.\n"
        "- If the caller is willing to join, ask them which date they prefer to start or join. Once they select a date, confirm it to them politely and let them know it has been noted on their profile.\n"
        "- IMMEDIATELY after confirming their joining date, ask: 'Would you like us to give you a reminder call one day before your joining date?' — Wait for their response.\n"
        "  - If they say YES to the reminder call: acknowledge warmly (e.g., 'Great, I will arrange a reminder call for you the day before your joining date.') and then close the call politely.\n"
        "  - If they say NO to the reminder call: acknowledge politely (e.g., 'No problem at all, we will see you on your joining date.') and then close the call politely.\n"
        "- If the caller wants a follow-up call, callback, or wishes to delay, ask them politely for the specific reason for their delay (e.g., exams, personal commitments) and ask what date/time would be best for a callback. Keep it warm and understanding.\n"
        "- Never mention any counselor names, staff names, or any person's name other than the customer's name.\n"
    )
    base_prompt += counseling_instructions

    # --- Inject DigiDARA knowledge base into the system prompt at call start.
    # Uses a fast targeted lookup for the most relevant FAQ chunks only.
    # This runs ONCE per call (here in voice_welcome), then the conversation
    # history carries context forward — no repeated RAG calls per turn.
    try:
        if selected_lang == "tamil":
            from app.livekit_agent.memory_kb import search as kb_search
            startup_query = f"DigiDara AI course internship fees duration placement contact {investigated_course or ''}"
            context = kb_search(startup_query, lang="ta", top_k=3)
            if context:
                base_prompt += (
                    "\n\nSTARTUP TAMIL KNOWLEDGE CONTEXT:\n"
                    "Use this only when relevant to the customer's question. "
                    "If the customer asks something specific, the live per-question knowledge lookup will add more context.\n"
                    f"{context}"
                )
        else:
            from app.services import rag_service
            if rag_service.is_available():
                # Pull top FAQ + company chunks as a compact context block
                startup_chunks = rag_service.retrieve(
                    f"DigiDARA {customer_name} {investigated_course or ''}",
                    collections=["company", "courses", "services", "contact", "internships"],
                    top_k=5,
                    max_distance=1.8,
                )
                if startup_chunks:
                    context = rag_service.build_context_block(startup_chunks[:8])
                    if context:
                        base_prompt += f"\n\n{context}"
    except Exception as rag_err:
        print(f"[media_stream] RAG pre-load failed: {rag_err}")
    # the assistant context so it can personalize the conversation instead of
    # starting from zero every time (e.g. "As we discussed last time, you were
    # interested in the AI course starting next month...").
    try:
        from app.services.memory_service import build_memory_context, get_memory
        memory_conn = get_db_connection()
        customer_memory = get_memory(memory_conn, customer_id)
        memory_conn.close()
        memory_context = build_memory_context(customer_memory)
        if memory_context and selected_lang != "tamil":
            base_prompt += f"\n\n{memory_context}"
    except Exception as mem_err:
        print(f"[media_stream] Failed to load customer memory: {mem_err}")
    
    # State variables
    stream_sid = None
    call_sid = None
    stt_confidences = []
    pcm_buffer = bytearray()
    silence_samples = 0
    speech_frame_count = 0
    speaking_state = False
    last_user_transcript = ""
    last_transcript_at = 0.0
    repeat_prompt_count = 0
    
    # Generation task control
    ai_task = None
    welcome_task = None
    keepalive_task = None
    
    # VAD Constants
    RMS_THRESHOLD = int(os.getenv("RMS_THRESHOLD", "500"))
    SILENCE_TIMEOUT_FRAMES = int(os.getenv("SILENCE_TIMEOUT_FRAMES", "45"))  # 20ms frames; 45 ~= 0.9s
    MAX_SPEECH_FRAMES = int(os.getenv("MAX_SPEECH_FRAMES", "240"))  # 20ms frames; 240 ~= 4.8s
    MIN_SPEECH_BYTES = int(os.getenv("MIN_SPEECH_BYTES", "1600"))  # 8kHz PCM16; 1600 ~= 0.1s
    MAX_TAMIL_REPEAT_PROMPTS = int(os.getenv("TAMIL_MAX_REPEAT_PROMPTS", "4"))
    
    # Track conversation history
    cursor.execute(
        "SELECT speaker, message FROM conversations WHERE customer_id = %s ORDER BY id ASC",
        (customer_id,)
    )
    rows = cursor.fetchall()
    history = []
    for row in rows:
        role = "assistant" if row["speaker"] == "assistant" else "user"
        history.append({"role": role, "content": row["message"]})
        
    db.close()

    async def generate_and_stream_response(user_text, is_first=False):
        nonlocal stream_sid, history, repeat_prompt_count, last_user_transcript, last_transcript_at
        print(f"Generating response for: '{user_text}'")
        repeat_prompt_count = 0
        last_user_transcript = user_text
        last_transcript_at = asyncio.get_running_loop().time()

        db_conn = get_db_connection()
        try:
            if not is_first:
                # Save user message to database
                save_conversation(db_conn, customer_id, "user", user_text)
                history.append({"role": "user", "content": user_text})

            # Format history for the LLM call
            hist_to_send = []
            history_window = history[-10:] if selected_lang == "tamil" else history
            for msg in history_window:
                content = msg["content"] or ""
                if selected_lang == "tamil" and len(content) > 400:
                    content = content[:400]
                hist_to_send.append({"role": msg["role"], "content": content})
            if not is_first and len(hist_to_send) > 0:
                hist_to_send.pop()  # Remove current user_text which is passed separately

            # --- Pipelined streaming: sentence N's TTS runs while sentence
            # N+1 is still being generated by the LLM, instead of waiting
            # for the ENTIRE reply before any audio starts. This is the
            # single biggest latency improvement in the call loop. A small
            # asyncio.Queue connects the LLM token-stream "producer" to a
            # TTS "consumer" task running concurrently.
            sentence_queue: asyncio.Queue = asyncio.Queue()
            full_reply_parts: list = []

            async def on_sentence(sentence: str):
                full_reply_parts.append(sentence)
                await sentence_queue.put(sentence)

            async def speak_chunk(text):
                nonlocal stream_sid
                if not text.strip():
                    return
                print(f"Synthesizing TTS chunk: '{text}'")
                try:
                    if lang_code == "ta-IN":
                        from app.services.gemini_service import text_to_speech_async as _ms_tts
                        audio_bytes = await _ms_tts(text, language_code=lang_code, speaker=TAMIL_TTS_SPEAKER)
                    else:
                        from app.services.elevenlabs_service import text_to_speech_elevenlabs_async as _ms_tts
                        audio_bytes = await _ms_tts(text)
                    sr = audio_utils.get_wav_sample_rate(audio_bytes)
                    raw_pcm = audio_utils.wav_to_raw_pcm(audio_bytes)
                    pcm_8k = audio_utils.resample_pcm(raw_pcm, sr, 8000)
                    mulaw_data = audio_utils.pcm2ulaw(pcm_8k)

                    # Send to Twilio in small chunks
                    chunk_size = 320
                    for idx in range(0, len(mulaw_data), chunk_size):
                        if asyncio.current_task().cancelled():
                            print("TTS chunk transmission cancelled.")
                            return
                        chunk = mulaw_data[idx : idx + chunk_size]
                        payload = base64.b64encode(chunk).decode("utf-8")
                        await websocket.send_json({
                            "event": "media",
                            "streamSid": stream_sid,
                            "media": {
                                "payload": payload
                            }
                        })
                        await asyncio.sleep(0.03)
                    if stream_sid:
                        await websocket.send_json({
                            "event": "mark",
                            "streamSid": stream_sid,
                            "mark": {"name": "tts-complete"}
                        })
                except Exception as tts_err:
                    print("TTS streaming error:", tts_err)

            async def tts_consumer():
                """Pulls completed sentences off the queue and speaks them
                in order, as soon as each becomes available — runs
                concurrently with the LLM still streaming later sentences."""
                while True:
                    sentence = await sentence_queue.get()
                    if sentence is None:  # sentinel: LLM stream finished
                        break
                    if asyncio.current_task().cancelled():
                        return
                    await speak_chunk(sentence)

            from app.services.groq_service import stream_response

            consumer_task = asyncio.create_task(tts_consumer())
            try:
                ai_reply = await stream_response(
                    base_prompt,
                    user_text,
                    hist_to_send,
                    on_sentence=on_sentence,
                    language=selected_lang,
                )
            finally:
                await sentence_queue.put(None)  # tell the consumer to stop
                await consumer_task

            ai_reply = (ai_reply or "").strip()

            if ai_reply:
                save_conversation(db_conn, customer_id, "assistant", ai_reply)
                history.append({"role": "assistant", "content": ai_reply})

                is_goodbye = any(word in ai_reply.lower() for word in ["goodbye", "bye", "take care", "have a nice day", "நன்றி", "போய் வருகிறேன்", "சென்று வருகிறேன்"])
                if is_goodbye:
                    await asyncio.sleep(3.0)
                    print("Goodbye detected, closing call stream.")
                    await websocket.send_json({
                        "event": "clear",
                        "streamSid": stream_sid
                    })
                    await websocket.close()
        except asyncio.CancelledError:
            print("AI generation task cancelled.")
        except Exception as e:
            print("Error in response generation loop:", e)
            if selected_lang == "tamil":
                fallback_reply = _deterministic_tamil_reply(user_text)
                if not fallback_reply:
                    lower_user = (user_text or "").lower()
                    if any(word in lower_user for word in ["யாரு", "who", "நீங்க", "நீ"]):
                        fallback_reply = "நான் DigiDara Technologiesலிருந்து பேசுறேன். Course அல்லது internship பற்றி உங்களுக்கு என்ன தெரிஞ்சுக்கணும்?"
                    elif any(word in lower_user for word in ["எப்படி", "how are", "நலமா"]):
                        fallback_reply = "நல்லா இருக்கேன், நன்றி. நீங்க எந்த course பற்றி தெரிஞ்சுக்க விரும்புறீங்க?"
                    else:
                        fallback_reply = "சரிங்க, நான் கேட்டேன். Course details, joining date, இல்ல reminder call பற்றி எது வேண்டுமோ கேளுங்க."
                await speak_direct_text(fallback_reply)
        finally:
            db_conn.close()

    async def play_cached_tamil_fallback(key: str) -> bool:
        nonlocal stream_sid
        if selected_lang != "tamil" or not stream_sid:
            return False
        audio_path = os.path.join(os.getcwd(), "audio_cache", _tamil_fallback_filename(key))
        if not os.path.exists(audio_path):
            print(f"[media_stream] Cached Tamil fallback missing: {audio_path}")
            return False
        try:
            with open(audio_path, "rb") as f:
                wav_data = f.read()
            sr = audio_utils.get_wav_sample_rate(wav_data)
            raw_pcm = audio_utils.wav_to_raw_pcm(wav_data)
            pcm_8k = audio_utils.resample_pcm(raw_pcm, sr, 8000)
            mulaw_data = audio_utils.pcm2ulaw(pcm_8k)
            for idx in range(0, len(mulaw_data), 320):
                payload = base64.b64encode(mulaw_data[idx:idx + 320]).decode("utf-8")
                await websocket.send_json({
                    "event": "media",
                    "streamSid": stream_sid,
                    "media": {"payload": payload},
                })
                await asyncio.sleep(0.03)
            return True
        except Exception as e:
            print(f"[media_stream] Cached Tamil fallback playback failed: {e}")
            return False

    async def speak_direct_text(text: str):
        nonlocal stream_sid
        if not text.strip() or not stream_sid:
            return
        try:
            if lang_code == "ta-IN":
                from app.services.gemini_service import text_to_speech_async as _direct_tts
                audio_bytes = await _direct_tts(text, language_code=lang_code, speaker=TAMIL_TTS_SPEAKER)
            else:
                from app.services.elevenlabs_service import text_to_speech_elevenlabs_async as _direct_tts
                audio_bytes = await _direct_tts(text)

            sr = audio_utils.get_wav_sample_rate(audio_bytes)
            raw_pcm = audio_utils.wav_to_raw_pcm(audio_bytes)
            pcm_8k = audio_utils.resample_pcm(raw_pcm, sr, 8000)
            mulaw_data = audio_utils.pcm2ulaw(pcm_8k)

            for idx in range(0, len(mulaw_data), 320):
                payload = base64.b64encode(mulaw_data[idx:idx + 320]).decode("utf-8")
                await websocket.send_json({
                    "event": "media",
                    "streamSid": stream_sid,
                    "media": {"payload": payload},
                })
                await asyncio.sleep(0.03)
        except Exception as e:
            print(f"Direct TTS repeat prompt failed: {e}")
            if selected_lang == "tamil":
                fallback_key = "generic_greeting" if ("DigiDara" in text or "டிஜிடாரா" in text or "டிஜி" in text) else "media_repeat"
                await play_cached_tamil_fallback(fallback_key)

    async def play_welcome_greeting():
        nonlocal stream_sid
        for _ in range(100):
            if stream_sid:
                break
            await asyncio.sleep(0.05)
        if not stream_sid:
            print("[media_stream] No streamSid received; cannot play welcome greeting.")
            return
            
        print("Playing welcome greeting...")
        audio_dir = os.path.join(os.getcwd(), "audio_cache")
        suffix = _tamil_cache_suffix(selected_lang)
        pregen_audio = f"first_greeting_{customer_id}_{campaign_id}{suffix}.wav"
        pregen_txt = f"first_greeting_{customer_id}_{campaign_id}{suffix}.txt"
        
        pregen_audio_path = os.path.join(audio_dir, pregen_audio)
        pregen_txt_path = os.path.join(audio_dir, pregen_txt)
        
        used_pregen = False
        if os.path.exists(pregen_audio_path) and os.path.exists(pregen_txt_path):
            try:
                with open(pregen_txt_path, "r", encoding="utf-8") as f:
                    ai_response = f.read().strip()
                with open(pregen_audio_path, "rb") as f:
                    wav_data = f.read()
                
                sr = audio_utils.get_wav_sample_rate(wav_data)
                raw_pcm = audio_utils.wav_to_raw_pcm(wav_data)
                pcm_8k = audio_utils.resample_pcm(raw_pcm, sr, 8000)
                mulaw_data = audio_utils.pcm2ulaw(pcm_8k)
                
                chunk_size = 320
                for idx in range(0, len(mulaw_data), chunk_size):
                    if asyncio.current_task().cancelled():
                        print("Welcome greeting transmission cancelled.")
                        return
                    chunk = mulaw_data[idx : idx + chunk_size]
                    payload = base64.b64encode(chunk).decode("utf-8")
                    await websocket.send_json({
                        "event": "media",
                        "streamSid": stream_sid,
                        "media": {
                            "payload": payload
                        }
                    })
                    await asyncio.sleep(0.03)
                if stream_sid:
                    await websocket.send_json({
                        "event": "mark",
                        "streamSid": stream_sid,
                        "mark": {"name": "welcome-complete"}
                    })
                
                db_conn = get_db_connection()
                customer_message = "I have chosen English. Please start the conversation based on your instructions." if selected_lang == "english" else "நான் தமிழைத் தேர்ந்தெடுத்துள்ளேன். தயவுசெய்து உரையாடலைத் தொடங்கவும்."
                save_conversation(db_conn, customer_id, "user", customer_message)
                save_conversation(db_conn, customer_id, "assistant", ai_response)
                history.append({"role": "user", "content": customer_message})
                history.append({"role": "assistant", "content": ai_response})
                db_conn.close()
                used_pregen = True
            except Exception as e:
                print("Failed playing pre-generated welcome greeting:", e)
                
        if not used_pregen:
            customer_message = "I have chosen English. Please start the conversation based on your instructions." if selected_lang == "english" else "நான் தமிழைத் தேர்ந்தெடுத்துள்ளேன். தயவுசெய்து உரையாடலைத் தொடங்கவும்."
            if selected_lang == "tamil":
                ai_response = f"வணக்கம் {customer_name}, நான் DigiDara Technologiesலிருந்து பேசுறேன். இப்போ பேசலாமா?"
                try:
                    db_conn = get_db_connection()
                    save_conversation(db_conn, customer_id, "user", customer_message)
                    save_conversation(db_conn, customer_id, "assistant", ai_response)
                    history.append({"role": "user", "content": customer_message})
                    history.append({"role": "assistant", "content": ai_response})
                    db_conn.close()
                except Exception as save_err:
                    print(f"[media_stream] Failed to save Tamil welcome: {save_err}")
                await speak_direct_text(ai_response)
            else:
                nonlocal ai_task
                ai_task = asyncio.create_task(generate_and_stream_response(customer_message, is_first=True))

    async def process_speech_buffer(reason: str):
        nonlocal ai_task, last_user_transcript, last_transcript_at, repeat_prompt_count
        audio_len = len(pcm_buffer)
        print(f"[media_stream] Processing speech buffer reason={reason} bytes={audio_len}")
        if audio_len < MIN_SPEECH_BYTES:
            print(f"[media_stream] Speech buffer too short; ignored bytes={audio_len}")
            pcm_buffer.clear()
            return

        raw_speech = bytes(pcm_buffer)
        pcm_buffer.clear()

        speech_16k = audio_utils.resample_8k_to_16k(raw_speech)
        wav_header = struct.pack(
            '<4sI4s4sIHHIIHH4sI',
            b'RIFF',
            len(speech_16k) + 36,
            b'WAVE',
            b'fmt ',
            16,
            1,
            1,
            16000,
            32000,
            2,
            16,
            b'data',
            len(speech_16k)
        )
        wav_bytes = wav_header + speech_16k

        from app.services.gemini_service import (
            speech_to_text_result_async,
            stream_speech_to_text_result_async,
        )
        try:
            stt_result = await speech_to_text_result_async(
                wav_bytes,
                filename="recording.wav",
                language_code=lang_code,
            )

            user_transcript = (stt_result.get("transcript") or "").strip()
            confidence = stt_result.get("confidence")
            if confidence is not None:
                stt_confidences.append(float(confidence))
            print(f"STT Transcript: '{user_transcript}' confidence={confidence}")

            if user_transcript:
                if selected_lang == "tamil" and _is_assistant_echo_or_noise(user_transcript):
                    print("[media_stream] Ignoring assistant echo/noisy Tamil transcript; keeping line open.")
                    return

                normalized_transcript = _normalize_voice_text(user_transcript)
                now = asyncio.get_running_loop().time()
                if (
                    normalized_transcript
                    and normalized_transcript == _normalize_voice_text(last_user_transcript)
                    and now - last_transcript_at < 2.0
                ):
                    print("[media_stream] Skipping immediate duplicate STT transcript.")
                    return

                if selected_lang != "tamil" and _should_reject_stt(user_transcript, confidence):
                    repeat_prompt_count += 1
                    ai_task = asyncio.create_task(
                        speak_direct_text("I'm sorry, I didn't catch that clearly. Could you repeat that?")
                    )
                    return

                repeat_prompt_count = 0
                last_user_transcript = user_transcript
                last_transcript_at = now
                direct_reply = _deterministic_tamil_reply(user_transcript) if selected_lang == "tamil" else None
                if direct_reply:
                    ai_task = asyncio.create_task(speak_direct_text(direct_reply))
                else:
                    ai_task = asyncio.create_task(generate_and_stream_response(user_transcript))
                return

            if selected_lang == "tamil":
                if repeat_prompt_count == 0:
                    repeat_prompt_count = 1
                    if not await play_cached_tamil_fallback("media_repeat"):
                        ai_task = asyncio.create_task(
                            speak_direct_text("சரி, நான் கேட்கிறேன். கொஞ்சம் தெளிவா சொல்லுங்க.")
                        )
                else:
                    print("[media_stream] Empty Tamil STT again; keeping line open without repeat prompt.")
                return

            repeat_prompt_count += 1
            ai_task = asyncio.create_task(
                speak_direct_text("I'm sorry, I didn't catch that clearly. Could you repeat that?")
            )
        except Exception as stt_err:
            print("STT Transcription failed:", stt_err)
            if selected_lang == "tamil":
                if repeat_prompt_count == 0:
                    repeat_prompt_count = 1
                    if not await play_cached_tamil_fallback("media_repeat"):
                        ai_task = asyncio.create_task(
                            speak_direct_text("சரி, நான் கேட்கிறேன். இன்னொரு முறை சொல்லுங்க.")
                        )
                else:
                    print("[media_stream] Tamil STT failed again; keeping line open without repeat prompt.")

    async def keepalive():
        nonlocal stream_sid
        try:
            while True:
                await asyncio.sleep(5)
                if stream_sid:
                    print("Sending keepalive mark event...")
                    try:
                        await websocket.send_json({
                            "event": "mark",
                            "streamSid": stream_sid,
                            "mark": {
                                "name": "keepalive"
                            }
                        })
                    except Exception as e:
                        print(f"Failed to send keepalive: {e}")
                        break
        except asyncio.CancelledError:
            pass

    try:
        welcome_task = asyncio.create_task(play_welcome_greeting())
        keepalive_task = asyncio.create_task(keepalive())
        
        async for message_str in websocket.iter_text():
            message = json.loads(message_str)
            event = message.get("event")
            
            if event == "start":
                start_info = message.get("start", {}) if isinstance(message.get("start"), dict) else {}
                stream_sid = message.get("streamSid") or start_info.get("streamSid")
                call_sid = start_info.get("callSid") or message.get("callSid")
                print(f"Twilio Media Stream started. Stream SID: {stream_sid}")
                
            elif event == "media":
                if not stream_sid:
                    stream_sid = message.get("streamSid") or (message.get("media", {}) or {}).get("streamSid")
                media = message.get("media", {})
                payload = media.get("payload")
                if not payload:
                    continue
                    
                ulaw_data = base64.b64decode(payload)
                pcm_data = audio_utils.ulaw2pcm(ulaw_data)
                rms = audio_utils.calculate_rms(pcm_data)
                
                if rms >= RMS_THRESHOLD:
                    silence_samples = 0
                    if not speaking_state:
                        if welcome_task and not welcome_task.done():
                            print("User interrupted welcome greeting. Cancelling greeting playback...")
                            welcome_task.cancel()
                            await websocket.send_json({
                                "event": "clear",
                                "streamSid": stream_sid
                            })

                        print(f"User started speaking (RMS: {rms:.1f})")
                        speaking_state = True
                        speech_frame_count = 0
                        
                        if ai_task and not ai_task.done():
                            print("User interrupted AI response. Cancelling generation...")
                            ai_task.cancel()
                            await websocket.send_json({
                                "event": "clear",
                                "streamSid": stream_sid
                            })
                        
                        pcm_buffer.clear()
                    
                    if speaking_state:
                        pcm_buffer.extend(pcm_data)
                        speech_frame_count += 1
                        if speech_frame_count >= MAX_SPEECH_FRAMES:
                            print(f"[media_stream] Max speech window reached ({speech_frame_count} frames); processing now.")
                            speaking_state = False
                            silence_samples = 0
                            speech_frame_count = 0
                            await process_speech_buffer("max_speech_window")
                else:
                    if speaking_state:
                        pcm_buffer.extend(pcm_data)
                        silence_samples += 1
                        if silence_samples >= SILENCE_TIMEOUT_FRAMES:
                            print(f"User finished speaking. Silence timeout reached (RMS: {rms:.1f}).")
                            speaking_state = False
                            silence_samples = 0
                            speech_frame_count = 0
                            
                            await process_speech_buffer("silence")
                                    
            elif event == "stop":
                print("Twilio Media Stream stopped.")
                break
                
    except WebSocketDisconnect:
        print("WebSocket disconnected.")
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        if ai_task and not ai_task.done():
            ai_task.cancel()
        if welcome_task and not welcome_task.done():
            welcome_task.cancel()
        if keepalive_task and not keepalive_task.done():
            keepalive_task.cancel()
        if call_sid and stt_confidences:
            try:
                avg_confidence = sum(stt_confidences) / len(stt_confidences)
                db_conn = get_db_connection()
                cursor = db_conn.cursor()
                cursor.execute(
                    "UPDATE call_logs SET stt_confidence_avg = %s WHERE call_sid = %s",
                    (avg_confidence, call_sid),
                )
                db_conn.commit()
                db_conn.close()
                print(f"Saved STT confidence avg={avg_confidence:.3f} for call_sid={call_sid}")
            except Exception as conf_err:
                print(f"Failed to save STT confidence average: {conf_err}")
        print("WebSocket connection closed, tasks cleaned up.")
