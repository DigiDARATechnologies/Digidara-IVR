import datetime
import json
from typing import List, Optional, Dict, Any

def row_to_dict(row: Any) -> Dict[str, Any]:
    """Helper to convert a row object to a standard Python dictionary."""
    if not row:
        return {}
    d = dict(row)
    for key, val in d.items():
        if isinstance(val, (datetime.datetime, datetime.date)):
            d[key] = val.strftime("%Y-%m-%d %H:%M:%S")
    return d

def create_call_log(
    conn: Any,
    organization_id: int,
    customer_id: int,
    campaign_id: int,
    call_sid: str,
    status: str,
    sheet_url: Optional[str] = None,
    sheet_row: Optional[int] = None,
    call_path: str = "openai_realtime",
    tts_provider: str = "openai",
    provider: str = "plivo",
    provider_request_id: Optional[str] = None,
    provider_call_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    provider_metadata: Optional[Dict[str, Any]] = None,
    failure_reason: Optional[str] = None,
) -> Dict[str, Any]:
    """Insert a call log, defaulting to the unified OpenAI Realtime path."""
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO call_logs (organization_id,customer_id,campaign_id,call_sid,status,call_status,
           sheet_url, sheet_row, call_path, tts_provider, language, provider,
           provider_request_id, provider_call_id, correlation_id, provider_metadata,
           failure_reason)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
             COALESCE((SELECT NULLIF(LOWER(language),'') FROM customers WHERE id=%s AND organization_id=%s),'english'),
             %s,%s,%s,%s,%s,%s)""",
        (
            organization_id, customer_id, campaign_id, call_sid, status, status,
            sheet_url, sheet_row, call_path, tts_provider, customer_id, organization_id,
            provider, provider_request_id,
            provider_call_id, correlation_id,
            json.dumps(provider_metadata or {}, ensure_ascii=False), failure_reason,
        )
    )
    conn.commit()
    new_id = cursor.lastrowid
    return get_call_log_by_id(conn, new_id, organization_id)

def get_call_log_by_id(
    conn: Any, log_id: int, organization_id: int,
) -> Optional[Dict[str, Any]]:
    """Retrieves a single call log by its database ID."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM call_logs WHERE id = %s AND organization_id = %s",
        (log_id, organization_id)
    )
    row = cursor.fetchone()
    if row:
        return row_to_dict(row)
    return None


def get_call_log_by_sid(conn: Any, call_sid: str) -> Optional[Dict[str, Any]]:
    """Compatibility lookup across neutral IDs and the historical call_sid."""
    cursor = conn.cursor()
    cursor.execute(
        """SELECT * FROM call_logs
           WHERE provider_call_id=%s OR provider_request_id=%s OR call_sid=%s
           ORDER BY id DESC LIMIT 1""",
        (call_sid, call_sid, call_sid)
    )
    row = cursor.fetchone()
    if row:
        return row_to_dict(row)
    return None


def find_active_call(
    conn: Any, customer_id: int, campaign_id: int, organization_id: int,
) -> Optional[Dict[str, Any]]:
    cursor = conn.cursor()
    cursor.execute(
        """SELECT * FROM call_logs
           WHERE customer_id=%s AND campaign_id=%s AND organization_id=%s
             AND COALESCE(call_status,status) IN
                 ('queued','initiated','ringing','answered','in-progress','ongoing')
             AND created_at > NOW() - INTERVAL 2 HOUR
           ORDER BY id DESC LIMIT 1""",
        (customer_id, campaign_id, organization_id),
    )
    row = cursor.fetchone()
    return row_to_dict(row) if row else None


def bind_provider_call(
    conn: Any, correlation_id: str, call_id: str, provider_status: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    cursor = conn.cursor()
    cursor.execute(
        """UPDATE call_logs SET provider_call_id=%s, call_sid=%s,
           provider_status=COALESCE(%s,provider_status)
           WHERE correlation_id=%s""",
        (call_id, call_id, provider_status, correlation_id),
    )
    conn.commit()
    cursor.execute("SELECT * FROM call_logs WHERE correlation_id=%s", (correlation_id,))
    row = cursor.fetchone()
    return row_to_dict(row) if row else None


def update_selected_language(
    conn: Any,
    call_log_id: int,
    organization_id: int,
    customer_id: int,
    language: str,
) -> None:
    """Persist a signed DTMF language choice on both call and customer."""
    if language not in {"english", "tamil"}:
        raise ValueError("Unsupported call language")
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE customers SET language=%s WHERE id=%s AND organization_id=%s",
        (language, customer_id, organization_id),
    )
    cursor.execute(
        """UPDATE call_logs SET language=%s
           WHERE id=%s AND customer_id=%s AND organization_id=%s""",
        (language, call_log_id, customer_id, organization_id),
    )
    conn.commit()

def get_all_call_logs(
    conn: Any, organization_id: int, skip: int = 0, limit: int = 100,
) -> List[Dict[str, Any]]:
    """Retrieves a list of all call logs with pagination."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM call_logs WHERE organization_id=%s "
        "ORDER BY id DESC LIMIT %s OFFSET %s",
        (organization_id, limit, skip)
    )
    rows = cursor.fetchall()
    return [row_to_dict(row) for row in rows]

def update_call_log_status(conn: Any, call_sid: str, status: str) -> Optional[Dict[str, Any]]:
    """Updates the status of a call log matching call_sid."""
    cursor = conn.cursor()
    cursor.execute(
        """UPDATE call_logs SET status=%s,call_status=%s,
           started_at=COALESCE(started_at,IF(%s IN ('initiated','queued','ringing','in-progress'),NOW(),NULL)),
           answered_at=COALESCE(answered_at,IF(%s IN ('answered','in-progress'),NOW(),NULL)),
           provider_status=%s
           WHERE provider_call_id=%s OR provider_request_id=%s OR call_sid=%s""",
        (status, status, status.lower(), status.lower(), status, call_sid, call_sid, call_sid)
    )
    conn.commit()
    
    # Retrieve and return the updated log
    cursor.execute(
        """SELECT * FROM call_logs WHERE provider_call_id=%s
           OR provider_request_id=%s OR call_sid=%s ORDER BY id DESC LIMIT 1""",
        (call_sid, call_sid, call_sid),
    )
    row = cursor.fetchone()
    updated_log = row_to_dict(row) if row else None
    
    if updated_log and updated_log.get("sheet_url") and updated_log.get("sheet_row"):
        try:
            from app.services import google_sheets_service
            import threading
            
            clean_status = status.lower()
            if clean_status == "in-progress":
                display_status = "ongoing"
            elif clean_status in ["queued", "initiated", "ringing"]:
                display_status = "ongoing"
            else:
                display_status = clean_status
                
            feedback_data = {"status": display_status}
            threading.Thread(
                target=google_sheets_service.update_sheet_feedback,
                args=(updated_log["sheet_url"], int(updated_log["sheet_row"]), feedback_data),
                daemon=True
            ).start()
        except Exception as sheet_err:
            print("Failed to trigger Google Sheets status update thread:", sheet_err)
            
    return updated_log

def finalize_call_log(
    conn: Any,
    call_sid: str,
    status: str,
    duration: int,
    transcript: Optional[str] = None,
    customer_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Updates status, duration, transcript, and summary when a call finishes."""
    from app.services import callback_service, groq_service
    from app.services.call_summary import build_call_summary, parse_analysis_response

    cursor = conn.cursor()
    # Get the existing call log to find customer_id and created_at
    cursor.execute("SELECT * FROM call_logs WHERE call_sid = %s", (call_sid,))
    log = cursor.fetchone()
    if not log:
        return None
    
    customer_id = customer_id or log["customer_id"]
    created_at = log["created_at"]

    if transcript is None and log.get("transcript"):
        transcript = log.get("transcript")
    elif transcript is None:
        # Retrieve conversation history since the call started
        cursor.execute(
            "SELECT speaker, message FROM conversations WHERE customer_id = %s AND timestamp >= %s ORDER BY id ASC",
            (customer_id, created_at)
        )
        conversations = cursor.fetchall()

        transcript = ""
        for c in conversations:
            transcript += f"{c['speaker']}: {c['message']}\n"
        
    summary = (log.get("summary") or "").strip()
    quick_summary = (log.get("quick_summary") or "").strip()
    followup_date = "N/A"
    joining_date = "N/A"
    reminder_consent = "not_asked"
    reminder_call_date = "N/A"
    lead_score = log.get("lead_score")
    lead_status = log.get("lead_status")
    qualification = log.get("qualification")

    analysis_dict: Dict[str, Any] = {
        "summary": summary,
        "quick_summary": quick_summary,
    }
    summary_is_reusable = bool(
        summary and quick_summary and summary != "Summary generation failed."
    )
    already_finalized = bool(
        summary_is_reusable
        and str(log.get("call_status") or log.get("status") or "").lower()
        in {"completed", "busy", "no-answer", "canceled", "failed"}
    )
    if transcript and not summary_is_reusable:
        try:
            analysis_json = groq_service.analyze_conversation(transcript)
            analysis_dict = parse_analysis_response(analysis_json)
            followup_date = analysis_dict.get("followup_date", "N/A")
            joining_date = analysis_dict.get("joining_date", "N/A")
            reminder_consent = analysis_dict.get("reminder_consent", "not_asked")
            lead_score = analysis_dict.get("lead_score", lead_score)
            lead_status = analysis_dict.get("lead_status") or analysis_dict.get("status") or lead_status
            qualification = analysis_dict.get("qualification") or qualification

            if joining_date and joining_date != "N/A":
                try:
                    import datetime as dt_module
                    jd = dt_module.date.fromisoformat(joining_date)
                    reminder_call_date = (jd - dt_module.timedelta(days=1)).isoformat()
                except Exception:
                    reminder_call_date = "N/A"
        except Exception as e:
            print("Failed to generate summary:", e)

    from app.services.lead_scoring_policy import normalize_score, qualification_for_score
    lead_score = normalize_score(lead_score)
    # The numeric post-call score is canonical; derive its tier centrally so
    # model text and structured extraction cannot silently disagree.
    qualification = qualification_for_score(lead_score)

    summary, quick_summary = build_call_summary(
        analysis_dict, transcript or "", status
    )
    parsed_followup_date = callback_service.normalize_requested_date(followup_date)
    callback_required = bool(
        log.get("followup_required") or lead_status == "callback_requested"
    )

    cursor.execute(
        """UPDATE call_logs 
           SET status = %s, call_status = %s, duration = GREATEST(COALESCE(duration,0),%s),
               transcript = %s, summary = %s, quick_summary = %s,
               lead_score = %s, lead_status = %s, qualification = %s,
               followup_required = %s,
               followup_date = COALESCE(%s, followup_date),
               completed_at=CASE WHEN %s IN ('completed','busy','no-answer','canceled','failed') THEN NOW() ELSE completed_at END
           WHERE call_sid = %s""",
        (status, status, duration, transcript, summary, quick_summary,
         lead_score, lead_status, qualification, callback_required,
         parsed_followup_date, status.lower(), call_sid)
    )
    cursor.execute("SELECT * FROM call_logs WHERE call_sid = %s", (call_sid,))
    row = cursor.fetchone()
    updated_log = row_to_dict(row) if row else None

    if not already_finalized and updated_log:
        try:
            from app.services import crm_outbox_service
            crm_outbox_service.emit_call_completed(conn, updated_log, commit=False)
        except Exception as crm_err:
            print(f"[finalize_call_log] Failed to emit CRM outbox event: {type(crm_err).__name__}")
    # Commit the terminal call state and its outbox event atomically.
    conn.commit()

    # Realtime finalization and Twilio's completed callback can both arrive.
    # The second event may update authoritative duration/status above, but must
    # not re-run sheet queues, lead extraction, or replace the accepted summary.
    if already_finalized:
        return updated_log

    if callback_required and updated_log:
        try:
            callback_service.ensure_for_call(
                conn,
                organization_id=int(updated_log["organization_id"]),
                call_log_id=int(updated_log["id"]),
                requested_date=parsed_followup_date,
                source="post_call_analysis",
            )
        except Exception as callback_err:
            print(f"[finalize_call_log] Failed to create callback task: {callback_err}")

    if updated_log and updated_log.get("sheet_url") and updated_log.get("sheet_row"):
        try:
            feedback_data = {
                "status": updated_log.get("status") or updated_log.get("call_status") or "",
                "duration": str(updated_log.get("duration") or 0),
                "summary": updated_log.get("summary") or "",
                "transcript": updated_log.get("transcript") or "",
                "conversation": transcript,
                "followup_date": followup_date,
                "joining_date": joining_date,
                "reminder_consent": reminder_consent,
                "reminder_call_date": reminder_call_date,
            }
            import threading
            threading.Thread(
                target=update_feedback_and_trigger_next,
                args=(
                    updated_log["sheet_url"],
                    int(updated_log["sheet_row"]),
                    feedback_data,
                    int(updated_log["campaign_id"]),
                    int(updated_log["organization_id"]),
                ),
                daemon=True
            ).start()
        except Exception as sheet_err:
            print("Failed to trigger Google Sheets update and queue thread:", sheet_err)

    # --- Lead extraction: pull structured fields (phone, company, requirement,
    # budget, timeline) + a 0-100 score from the transcript using a dedicated
    # LLM pass, then update structured customer memory for continuity.
    if transcript and status in ("completed", "busy", "no-answer"):
        try:
            from app.services.lead_extraction_service import extract_lead_fields
            from app.services.memory_service import extract_questions_from_transcript, upsert_memory

            lead_fields = extract_lead_fields(transcript)

            # Structured extraction owns only the descriptive fields. The
            # accepted call_logs score/tier is copied verbatim as the single
            # persisted source of truth.
            effective_score = (updated_log or {}).get("lead_score")
            effective_qualification = (updated_log or {}).get("qualification")

            try:
                cursor.execute("""
                    INSERT INTO lead_qualifications
                      (call_log_id, customer_id, extracted_name, extracted_phone,
                       company, requirement, budget, timeline, lead_score, qualification)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    log["id"],
                    customer_id,
                    lead_fields.get("name"),
                    lead_fields.get("phone"),
                    lead_fields.get("company"),
                    lead_fields.get("requirement"),
                    lead_fields.get("budget"),
                    lead_fields.get("timeline"),
                    effective_score,
                    effective_qualification,
                ))
                conn.commit()
            except Exception as db_err:
                print(f"[finalize_call_log] Failed to save lead_qualifications row: {db_err}")

            new_questions = extract_questions_from_transcript(transcript)
            upsert_memory(
                conn,
                customer_id=customer_id,
                name=lead_fields.get("name"),
                intent=lead_fields.get("requirement"),
                new_questions=new_questions,
                lead_status=effective_qualification,
                summary=quick_summary or summary or None,
            )
        except Exception as lead_err:
            print(f"[finalize_call_log] Lead extraction / memory update failed: {lead_err}")

    return updated_log



def update_feedback_and_trigger_next(
    sheet_url: str, row_number: int, feedback_data: Dict[str, Any],
    campaign_id: int, organization_id: int,
) -> None:
    """
    Updates the feedback for the completed call in Google Sheets,
    and then triggers the next queued call from the same sheet.
    """
    from app.services import bulk_upload_service, google_sheets_service, telephony_service
    try:
        if bulk_upload_service.is_upload_reference(sheet_url):
            bulk_upload_service.update_feedback(sheet_url, row_number, feedback_data)
        else:
            google_sheets_service.update_sheet_feedback(sheet_url, row_number, feedback_data)
    except Exception as e:
        print(f"Error updating sheet feedback: {str(e)}")
        
    try:
        telephony_service.trigger_next_queued_call(
            sheet_url, campaign_id, organization_id
        )
    except Exception as e:
        print(f"Error triggering next queued call: {str(e)}")
