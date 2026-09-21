"""Re-score a call from its full audio recording when part of the
conversation happened after a human transfer.

The AI's own turn-by-turn transcript stops the moment it hands off to a
human, so a call qualified from that transcript alone is judged on an
incomplete picture -- often just a few seconds of "which department do you
need". This re-transcribes the complete recording (AI portion and the
transferred human conversation) and re-runs the same qualification pipeline
finalize_call_log already uses, so hot/warm/cold reflects what was actually
discussed. Only ever runs for calls that had a completed human transfer;
everything else already has a full transcript from the AI itself.
"""

from __future__ import annotations

import time
from typing import Any

import requests

from app.services import crm_outbox_service, groq_service
from app.services.call_summary import build_call_summary, parse_analysis_response
from app.services.lead_scoring_policy import normalize_score, qualification_for_score
from app.services.telephony import get_telephony_provider
from app.services.tenant_credentials_service import resolve_openai_api_key

MAX_RECORDING_BYTES = 25 * 1024 * 1024  # 25 MB OpenAI Whisper limit


def _transcribe(
    api_key: str,
    audio_bytes: bytes,
    content_type: str,
    language: str | None = None,
    prompt: str | None = None,
) -> str:
    extension = "mp3" if "mp3" in content_type or "mpeg" in content_type else "wav"
    data: dict[str, Any] = {"model": "whisper-1"}
    if language:
        data["language"] = language
    if prompt:
        data["prompt"] = prompt

    last_exc = None
    for attempt in range(2):
        try:
            response = requests.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (f"call.{extension}", audio_bytes, content_type)},
                data=data,
                timeout=120,
            )
            response.raise_for_status()
            return (response.json().get("text") or "").strip()
        except requests.RequestException as exc:
            last_exc = exc
            if attempt == 0:
                time.sleep(2.0)

    if last_exc:
        raise last_exc
    return ""


def reanalyze_transferred_call(
    conn: Any,
    organization_id: int,
    call_log_id: int,
    poll_attempts: int = 3,
    poll_delay_seconds: float = 1.0,
) -> bool:
    """Best-effort; returns True only if the call was re-scored or already re-analyzed."""
    cursor = conn.cursor()

    transfer = None
    for attempt in range(max(1, poll_attempts)):
        cursor.execute(
            """SELECT id, status FROM call_transfers
                 WHERE organization_id=%s AND call_log_id=%s
                 ORDER BY id DESC LIMIT 1""",
            (organization_id, call_log_id),
        )
        transfer = cursor.fetchone()
        if not transfer:
            return False
        transfer_status = transfer.get("status")
        if transfer_status in {None, "completed"}:
            break
        # Fallback: if transfer was answered and parent call in call_logs is already
        # in a terminal state, the human leg has completed even if /transfer-action lags.
        if transfer_status == "answered":
            cursor.execute(
                """SELECT status, call_status FROM call_logs
                     WHERE id=%s AND organization_id=%s""",
                (call_log_id, organization_id),
            )
            call_row = cursor.fetchone() or {}
            terminal_status = str(call_row.get("call_status") or call_row.get("status") or "").lower()
            if terminal_status in {"completed", "busy", "no-answer", "canceled", "failed"}:
                break
        if attempt < poll_attempts - 1:
            time.sleep(poll_delay_seconds)

    if not transfer or (transfer.get("status") not in {None, "completed", "answered"}):
        return False

    cursor.execute(
        """SELECT customer_id, provider_recording_id, transcript, status, call_status, language
             FROM call_logs WHERE id=%s AND organization_id=%s""",
        (call_log_id, organization_id),
    )
    log = cursor.fetchone()
    if not log or not log.get("provider_recording_id"):
        return False

    # Idempotency guard: prevent duplicate Whisper and Groq calls if already re-analyzed
    ai_transcript = (log.get("transcript") or "").strip()
    if "[Full call recording transcript" in ai_transcript:
        print(f"[call_recording_analysis] Skipped call {call_log_id}: already reanalyzed")
        return True

    api_key = resolve_openai_api_key(conn, organization_id)
    if not api_key:
        print(f"[call_recording_analysis] Skipped call {call_log_id}: OPENAI_API_KEY not configured")
        return False

    try:
        provider = get_telephony_provider(conn, organization_id)
        audio_bytes, content_type = provider.get_recording(log["provider_recording_id"])

        # Guard against Whisper 25 MB payload limit on long calls
        if len(audio_bytes) > MAX_RECORDING_BYTES:
            size_mb = round(len(audio_bytes) / (1024 * 1024), 1)
            print(
                f"[call_recording_analysis] Skipped call {call_log_id}: "
                f"recording size ({size_mb} MB) exceeds Whisper 25 MB limit"
            )
            return False

        # Multilingual hinting based on call language
        call_language = str(log.get("language") or "").strip().lower()
        if call_language == "tamil":
            whisper_lang = "ta"
            whisper_prompt = "DigiDARA AI voice calling, course enquiry, fees, Tamil and English conversation."
        elif call_language == "english":
            whisper_lang = "en"
            whisper_prompt = "DigiDARA AI voice calling, course enquiry, admissions and fees conversation."
        else:
            whisper_lang = None
            whisper_prompt = "DigiDARA AI voice calling conversation."

        recording_transcript = _transcribe(
            api_key,
            audio_bytes,
            content_type,
            language=whisper_lang,
            prompt=whisper_prompt,
        )
        if not recording_transcript:
            return False

        full_transcript = (
            f"{ai_transcript}\n\n[Full call recording transcript, includes the "
            f"conversation after human transfer]\n{recording_transcript}"
            if ai_transcript else recording_transcript
        )

        analysis_json = None
        for attempt in range(2):
            try:
                analysis_json = groq_service.analyze_conversation(full_transcript)
                break
            except Exception as llm_exc:
                if attempt == 0:
                    time.sleep(2.0)
                else:
                    raise llm_exc

        analysis = parse_analysis_response(analysis_json)
        lead_score = normalize_score(analysis.get("lead_score"))
        qualification = qualification_for_score(lead_score)
        lead_status = analysis.get("lead_status") or analysis.get("status")
        status = log.get("call_status") or log.get("status") or "completed"
        summary, quick_summary = build_call_summary(analysis, full_transcript, status)
        cursor.execute(
            """UPDATE call_logs SET transcript=%s, summary=%s, quick_summary=%s,
                 lead_score=COALESCE(%s,lead_score), qualification=COALESCE(%s,qualification),
                 lead_status=COALESCE(%s,lead_status)
               WHERE id=%s AND organization_id=%s""",
            (
                full_transcript, summary, quick_summary, lead_score, qualification,
                lead_status, call_log_id, organization_id,
            ),
        )
        customer_id = log.get("customer_id")
        if customer_id and qualification in {"hot", "warm", "cold"}:
            try:
                cursor.execute(
                    """UPDATE customers
                       SET customer_status=%s, updated_at=CURRENT_TIMESTAMP
                       WHERE id=%s AND organization_id=%s
                         AND (customer_status IS NULL OR customer_status NOT IN ('do_not_call', 'converted'))""",
                    (qualification, customer_id, organization_id),
                )
            except Exception as cust_err:
                print(f"[call_recording_analysis] Failed to sync customer status: {cust_err}")

        cursor.execute(
            "SELECT * FROM call_logs WHERE id=%s AND organization_id=%s",
            (call_log_id, organization_id),
        )
        updated_log = cursor.fetchone()
        if updated_log:
            try:
                crm_outbox_service.emit_call_completed(conn, updated_log, commit=False)
            except Exception as crm_exc:
                print(f"[call_recording_analysis] CRM outbox re-emit failed for call {call_log_id}: {type(crm_exc).__name__}: {crm_exc}")
        conn.commit()
        print(
            f"[call_recording_analysis] Re-scored call {call_log_id} from full recording | "
            f"qualification={qualification} lead_score={lead_score}"
        )
        return True
    except Exception as exc:
        print(f"[call_recording_analysis] Failed for call {call_log_id}: {type(exc).__name__}: {exc}")
        return False
