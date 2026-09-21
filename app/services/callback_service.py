"""Tenant-safe callback task persistence and operator workflow."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Optional


VALID_STATUSES = {"pending", "assigned", "completed", "cancelled"}
_SELECT = """
    SELECT fr.id, fr.organization_id, fr.customer_id, fr.campaign_id,
           fr.source_call_log_id, fr.reminder_type, fr.source,
           fr.requested_date, fr.scheduled_at, fr.timezone, fr.status,
           fr.assigned_user_id, au.full_name AS assigned_user_name,
           fr.notes, fr.completed_at, fr.completed_by_user_id,
           fr.created_at, fr.updated_at,
           c.name AS customer_name, c.phone AS customer_phone,
           cl.quick_summary AS call_summary, cl.lead_score, cl.qualification
      FROM followup_reminders fr
      JOIN customers c ON c.id=fr.customer_id AND c.organization_id=fr.organization_id
 LEFT JOIN call_logs cl ON cl.id=fr.source_call_log_id AND cl.organization_id=fr.organization_id
 LEFT JOIN app_users au ON au.id=fr.assigned_user_id AND au.organization_id=fr.organization_id
"""


def _date_value(value: Any) -> Optional[date]:
    if value in (None, "", "N/A"):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except (TypeError, ValueError):
        return None


def normalize_requested_date(value: Any) -> Optional[date]:
    return _date_value(value)


def get_by_id(conn: Any, organization_id: int, callback_id: int) -> Optional[dict[str, Any]]:
    cursor = conn.cursor()
    cursor.execute(
        _SELECT + " WHERE fr.id=%s AND fr.organization_id=%s",
        (callback_id, organization_id),
    )
    return cursor.fetchone()


def list_callbacks(
    conn: Any,
    organization_id: int,
    *,
    status: Optional[str] = None,
    assigned_user_id: Optional[int] = None,
    search: Optional[str] = None,
    limit: int = 100,
    skip: int = 0,
) -> list[dict[str, Any]]:
    conditions = ["fr.organization_id=%s"]
    params: list[Any] = [organization_id]
    if status:
        if status not in VALID_STATUSES:
            raise ValueError("Unknown callback status")
        conditions.append("fr.status=%s")
        params.append(status)
    if assigned_user_id is not None:
        conditions.append("fr.assigned_user_id=%s")
        params.append(assigned_user_id)
    if search:
        conditions.append("(c.name LIKE %s OR c.phone LIKE %s OR fr.notes LIKE %s)")
        term = f"%{search.strip()[:100]}%"
        params.extend((term, term, term))
    cursor = conn.cursor()
    cursor.execute(
        _SELECT
        + " WHERE " + " AND ".join(conditions)
        + " ORDER BY CASE WHEN fr.status IN ('pending','assigned') THEN 0 ELSE 1 END, "
          "COALESCE(fr.scheduled_at, TIMESTAMP(fr.requested_date), fr.created_at), fr.id DESC "
          "LIMIT %s OFFSET %s",
        params + [limit, skip],
    )
    return cursor.fetchall() or []


def summary(conn: Any, organization_id: int) -> dict[str, int]:
    cursor = conn.cursor()
    cursor.execute(
        """SELECT
             SUM(status='pending') AS pending,
             SUM(status='assigned') AS assigned,
             SUM(status='completed') AS completed,
             SUM(status IN ('pending','assigned') AND scheduled_at < NOW()) AS overdue,
             SUM(status IN ('pending','assigned') AND DATE(scheduled_at)=CURRENT_DATE()) AS due_today
           FROM followup_reminders WHERE organization_id=%s""",
        (organization_id,),
    )
    row = cursor.fetchone() or {}
    return {key: int(row.get(key) or 0) for key in ("pending", "assigned", "overdue", "due_today", "completed")}


def ensure_for_call(
    conn: Any,
    *,
    organization_id: int,
    call_log_id: int,
    requested_date: Any = None,
    source: str = "realtime",
) -> dict[str, Any]:
    """Idempotently create or enrich the callback task for one call."""
    cursor = conn.cursor()
    cursor.execute(
        """SELECT cl.id, cl.customer_id, cl.campaign_id, o.timezone
             FROM call_logs cl
             JOIN organizations o ON o.id=cl.organization_id
            WHERE cl.id=%s AND cl.organization_id=%s""",
        (call_log_id, organization_id),
    )
    call = cursor.fetchone()
    if not call:
        raise ValueError("Call log does not belong to the organization")
    parsed_date = _date_value(requested_date)
    idempotency_key = f"callback:call:{call_log_id}"
    cursor.execute(
        """INSERT INTO followup_reminders
             (organization_id,customer_id,campaign_id,source_call_log_id,
              reminder_type,source,requested_date,timezone,status,idempotency_key)
           VALUES (%s,%s,%s,%s,'callback',%s,%s,%s,'pending',%s)
           ON DUPLICATE KEY UPDATE
             requested_date=COALESCE(VALUES(requested_date),requested_date),
             source=CASE WHEN source='realtime' THEN source ELSE VALUES(source) END,
             updated_at=CURRENT_TIMESTAMP""",
        (
            organization_id, call["customer_id"], call.get("campaign_id"), call_log_id,
            source[:40], parsed_date, call.get("timezone") or "Asia/Kolkata", idempotency_key,
        ),
    )
    cursor.execute(
        _SELECT + " WHERE fr.idempotency_key=%s AND fr.organization_id=%s",
        (idempotency_key, organization_id),
    )
    callback = cursor.fetchone()
    if callback:
        try:
            from app.services import crm_outbox_service
            crm_outbox_service.emit_callback_required(conn, callback, commit=False)
        except Exception as exc:
            print(f"[callback] CRM outbox emission failed: {type(exc).__name__}")
    # The callback task and its outbox event become visible together.
    conn.commit()
    return callback


def ensure_for_call_sid(
    conn: Any, *, organization_id: int, call_sid: str, source: str = "realtime",
) -> Optional[dict[str, Any]]:
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM call_logs WHERE call_sid=%s AND organization_id=%s",
        (call_sid, organization_id),
    )
    row = cursor.fetchone()
    if not row:
        return None
    return ensure_for_call(
        conn, organization_id=organization_id, call_log_id=int(row["id"]), source=source,
    )


def update_callback(
    conn: Any,
    *,
    organization_id: int,
    callback_id: int,
    actor_user_id: int,
    changes: dict[str, Any],
) -> Optional[dict[str, Any]]:
    existing = get_by_id(conn, organization_id, callback_id)
    if not existing:
        return None
    fields: list[str] = []
    params: list[Any] = []
    if changes.get("assigned_user_id") is not None:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM app_users WHERE id=%s AND organization_id=%s AND is_active=TRUE",
            (changes["assigned_user_id"], organization_id),
        )
        if not cursor.fetchone():
            raise ValueError("Assigned user is not an active member of this organization")
        fields.append("assigned_user_id=%s")
        params.append(changes["assigned_user_id"])
        if not changes.get("status") and existing["status"] == "pending":
            changes["status"] = "assigned"
    elif changes.get("clear_assignee"):
        fields.append("assigned_user_id=NULL")
        if not changes.get("status") and existing["status"] == "assigned":
            changes["status"] = "pending"
    if changes.get("status") is not None:
        if changes["status"] not in VALID_STATUSES:
            raise ValueError("Unknown callback status")
        fields.append("status=%s")
        params.append(changes["status"])
        if changes["status"] == "completed":
            fields.extend(("completed_at=NOW()", "completed_by_user_id=%s"))
            params.append(actor_user_id)
        else:
            fields.extend(("completed_at=NULL", "completed_by_user_id=NULL"))
    if changes.get("requested_date") is not None:
        fields.append("requested_date=%s")
        params.append(changes["requested_date"])
    if changes.get("scheduled_at") is not None:
        fields.append("scheduled_at=%s")
        params.append(changes["scheduled_at"])
    elif changes.get("clear_schedule"):
        fields.append("scheduled_at=NULL")
    if changes.get("notes") is not None:
        fields.append("notes=%s")
        params.append(changes["notes"].strip() or None)
    if not fields:
        return existing
    cursor = conn.cursor()
    cursor.execute(
        f"UPDATE followup_reminders SET {', '.join(fields)} WHERE id=%s AND organization_id=%s",
        params + [callback_id, organization_id],
    )
    if changes.get("status") in {"completed", "cancelled"} and existing.get("source_call_log_id"):
        cursor.execute(
            "UPDATE call_logs SET followup_required=FALSE WHERE id=%s AND organization_id=%s",
            (existing["source_call_log_id"], organization_id),
        )
    elif changes.get("status") in {"pending", "assigned"} and existing.get("source_call_log_id"):
        cursor.execute(
            "UPDATE call_logs SET followup_required=TRUE WHERE id=%s AND organization_id=%s",
            (existing["source_call_log_id"], organization_id),
        )
    audit_metadata = {
        key: str(value) for key, value in changes.items()
        if key in {"status", "assigned_user_id", "clear_assignee", "requested_date", "scheduled_at", "clear_schedule"}
    }
    cursor.execute(
        """INSERT INTO audit_logs
             (organization_id,actor_user_id,action,resource_type,resource_id,result,metadata_json)
           VALUES (%s,%s,'callback_updated','followup_reminder',%s,'success',%s)""",
        (organization_id, actor_user_id, str(callback_id), json.dumps(audit_metadata)),
    )
    conn.commit()
    return get_by_id(conn, organization_id, callback_id)
