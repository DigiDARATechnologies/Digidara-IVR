"""Provider-neutral outbound calling and campaign queue orchestration."""

from __future__ import annotations

import hashlib
import os
import json
import re
import time
import uuid
from typing import Optional
from urllib.parse import urlencode

from dotenv import load_dotenv

from app.services import call_log_service
from app.services.call_guardrail_service import call_duration_limit_seconds
from app.services.telephony import get_telephony_provider


def _reload_env() -> None:
    load_dotenv(
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env")),
        override=True,
    )


def normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", (phone or "").strip())
    if not digits:
        raise ValueError("Phone number is empty")
    if len(digits) == 10:
        return f"+91{digits}"
    if digits.startswith("91") and len(digits) == 12:
        return f"+{digits}"
    return f"+{digits}"


def _public_base_url() -> str:
    return (os.getenv("WEBHOOK_BASE_URL") or "").strip().rstrip("/")


def is_suppressed(
    db, customer_id: int, organization_id: int,
    phone_number: Optional[str] = None,
) -> bool:
    """Return True if this customer must not be dialed.

    Checks both the per-customer do_not_call flag and the org-wide
    suppression_list (phone-hash), since duplicate customer records for the
    same real phone number are possible and either could carry the opt-out.
    """
    cursor = db.cursor()
    cursor.execute(
        "SELECT do_not_call,is_active,organization_id,phone FROM customers "
        "WHERE id=%s AND organization_id=%s",
        (customer_id, organization_id),
    )
    customer = cursor.fetchone() or {}
    if customer.get("do_not_call"):
        return True

    raw_phone = phone_number or customer.get("phone") or ""
    digits = re.sub(r"\D+", "", str(raw_phone))
    if not digits:
        return False
    phone_hash = hashlib.sha256(digits.encode("utf-8")).hexdigest()
    if not customer or not customer.get("organization_id"):
        return True
    org_id = int(customer["organization_id"])
    cursor.execute(
        "SELECT 1 FROM suppression_list WHERE organization_id=%s AND phone_hash=%s LIMIT 1",
        (org_id, phone_hash),
    )
    return cursor.fetchone() is not None


def has_owned_call_context(
    db, customer_id: int, campaign_id: int, organization_id: int,
) -> bool:
    """Require both call parents to belong to the authenticated organization."""
    cursor = db.cursor()
    cursor.execute(
        """SELECT 1 FROM customers c
           JOIN campaigns p ON p.id=%s AND p.organization_id=%s
           WHERE c.id=%s AND c.organization_id=%s LIMIT 1""",
        (campaign_id, organization_id, customer_id, organization_id),
    )
    return cursor.fetchone() is not None


def start_outbound_call(
    db,
    organization_id: int,
    customer_id: int,
    phone_number: str,
    campaign_id: int,
    sheet_url: Optional[str] = None,
    sheet_row: Optional[int] = None,
) -> dict:
    _reload_env()
    provider = get_telephony_provider(db, organization_id)
    base_url = _public_base_url()
    duration_limit = call_duration_limit_seconds()

    if not has_owned_call_context(
        db, customer_id, campaign_id, organization_id
    ):
        return {
            "message": "Customer or campaign is unavailable for this organization.",
            "provider": provider.name,
            "provider_call_id": None,
            "request_id": None,
            "call_sid": None,
            "status": "invalid_context",
        }

    if is_suppressed(db, customer_id, organization_id, phone_number):
        return {
            "message": "Customer is on the do-not-call list; call not placed.",
            "provider": provider.name,
            "provider_call_id": None,
            "request_id": None,
            "call_sid": None,
            "status": "suppressed",
        }

    existing = call_log_service.find_active_call(
        db, customer_id, campaign_id, organization_id
    )
    if existing:
        return {
            "message": "An active call already exists for this lead and campaign.",
            "provider": existing.get("provider") or "plivo",
            "provider_call_id": existing.get("provider_call_id"),
            "request_id": existing.get("provider_request_id"),
            "call_sid": existing.get("provider_call_id") or existing.get("call_sid"),
            "status": existing.get("call_status") or existing.get("status"),
            "log": existing,
        }

    correlation_id = uuid.uuid4().hex
    if not provider.is_configured() or not base_url or "your-" in base_url:
        request_id = f"sim_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        log = call_log_service.create_call_log(
            db, organization_id, customer_id, campaign_id, request_id, "simulated",
            sheet_url, sheet_row, provider=provider.name,
            provider_request_id=request_id, correlation_id=correlation_id,
            provider_metadata={"time_limit_seconds": duration_limit},
        )
        return {
            "message": (
                "Simulation mode — configure Plivo credentials and a public HTTPS/WSS "
                "WEBHOOK_BASE_URL to place a real call."
            ),
            "provider": provider.name,
            "provider_call_id": None,
            "request_id": request_id,
            "call_sid": request_id,
            "status": "simulated",
            "log": log,
        }

    query = urlencode({
        "customer_id": customer_id,
        "campaign_id": campaign_id,
        "correlation_id": correlation_id,
    })
    provisional_id = f"pending_{correlation_id}"
    log = call_log_service.create_call_log(
        db, organization_id, customer_id, campaign_id, provisional_id, "queued",
        sheet_url, sheet_row, provider=provider.name,
        correlation_id=correlation_id,
    )
    try:
        result = provider.create_call(
            to=normalize_phone(phone_number),
            answer_url=f"{base_url}/api/plivo/answer?{query}",
            ring_url=f"{base_url}/api/plivo/ring?{query}",
            hangup_url=f"{base_url}/api/plivo/hangup?{query}",
            fallback_url=f"{base_url}/api/plivo/fallback?{query}",
            time_limit_seconds=duration_limit,
        )
        cursor = db.cursor()
        cursor.execute(
            """UPDATE call_logs SET call_sid=%s,provider=%s,provider_request_id=%s,
               status='initiated',call_status='initiated',provider_status='initiated',
               provider_metadata=%s,started_at=COALESCE(started_at,NOW())
               WHERE id=%s""",
            (
                result.request_id, result.provider, result.request_id,
                json.dumps(
                    {**dict(result.metadata), "time_limit_seconds": duration_limit},
                    ensure_ascii=False,
                ),
                log["id"],
            ),
        )
        db.commit()
        log = call_log_service.get_call_log_by_id(
            db, log["id"], organization_id
        )
        return {
            "message": "Call initiated successfully",
            "provider": result.provider,
            "provider_call_id": result.call_id,
            "request_id": result.request_id,
            "call_sid": result.call_id or result.request_id,
            "status": "initiated",
            "log": log,
        }
    except Exception as exc:
        # Plivo's own validation messages describe the request the admin
        # just made (bad number, malformed URL, etc.) — safe to surface
        # directly instead of masking them behind the exception's class
        # name, which left failures undiagnosable without a live debugger.
        detail = str(exc).strip()
        safe_reason = f"Plivo call creation failed ({type(exc).__name__}): {detail}" if detail else f"Plivo call creation failed ({type(exc).__name__})"
        safe_reason = safe_reason[:500]
        cursor = db.cursor()
        cursor.execute(
            """UPDATE call_logs SET status='failed',call_status='failed',
               provider_status='failed',failure_reason=%s,completed_at=NOW()
               WHERE id=%s""",
            (safe_reason, log["id"]),
        )
        db.commit()
        return {
            "message": safe_reason,
            "provider": provider.name,
            "provider_call_id": None,
            "request_id": provisional_id,
            "call_sid": provisional_id,
            "status": "failed",
        }


def trigger_next_queued_call(
    sheet_url: str, campaign_id: int, organization_id: int,
) -> None:
    from app.database.db import get_db_connection
    from app.services import bulk_upload_service, customer_service, google_sheets_service

    if bulk_upload_service.is_upload_reference(sheet_url):
        read_rows, write_status = bulk_upload_service.read_rows, bulk_upload_service.update_status
    else:
        read_rows, write_status = google_sheets_service.read_sheet_data, google_sheets_service.update_sheet_status

    db = get_db_connection()
    try:
        for index, row in enumerate(read_rows(sheet_url) or []):
            status = (row.get("Status") or row.get("status") or "").strip().lower()
            if status not in {"queued", "queue", "pending", ""}:
                continue
            row_index = row.get("row_number") or (index + 2)
            phone = row.get("Phone") or row.get("phone") or ""
            if not phone:
                continue
            customer_id = customer_service.upsert_customer(
                db,
                organization_id=organization_id,
                name=row.get("Name") or row.get("name") or "",
                phone=phone,
                language=(row.get("Language") or row.get("language") or "english").lower(),
                investigated_course=row.get("Investigated Course") or row.get("investigated_course") or "",
                internship_or_course=row.get("Internship or Course") or row.get("internship_or_course") or "",
                course_duration=row.get("Course Duration") or row.get("course_duration") or "",
                sheet_url=sheet_url,
                sheet_row=row_index,
            )
            if is_suppressed(db, customer_id, organization_id, phone):
                write_status(sheet_url, row_index, "do_not_call")
                continue
            write_status(sheet_url, row_index, "calling")
            start_outbound_call(
                db, organization_id, customer_id, phone, campaign_id,
                sheet_url, row_index,
            )
            break
    finally:
        db.close()
