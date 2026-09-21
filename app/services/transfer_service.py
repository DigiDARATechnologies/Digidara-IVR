"""Tenant-safe operator initiated human handoff state machine."""

from __future__ import annotations

import json
from typing import Any, Optional


LIVE_STATUSES = {"in-progress", "answered", "ongoing", "active"}
FINAL_TRANSFER_STATUSES = {"completed", "failed", "cancelled"}

_TRANSFER_SELECT = """
    SELECT ct.id,ct.organization_id,ct.call_log_id,ct.destination_id,
           sd.name AS destination_name,sd.phone_e164 AS destination_phone,
           sd.department AS department,
           ct.status,ct.provider_call_id,ct.provider_bleg_id,
           ct.initiated_by_user_id,ct.failure_reason,ct.requested_at,
           ct.answered_at,ct.completed_at,ct.updated_at
      FROM call_transfers ct
      JOIN staff_destinations sd ON sd.id=ct.destination_id
       AND sd.organization_id=ct.organization_id
"""


def list_departments(conn: Any, organization_id: int, active_only: bool = False) -> list[dict[str, Any]]:
    cursor = conn.cursor()
    where = "d.organization_id=%s" + (" AND d.is_active=TRUE" if active_only else "")
    cursor.execute(
        f"""SELECT d.id, d.organization_id, d.name, d.description, d.is_active,
                  d.created_at, d.updated_at,
                  COUNT(CASE WHEN sd.is_active=TRUE THEN sd.id END) AS member_count
             FROM departments d
        LEFT JOIN staff_destinations sd ON sd.organization_id=d.organization_id AND LOWER(TRIM(sd.department))=LOWER(TRIM(d.name))
            WHERE {where}
         GROUP BY d.id, d.organization_id, d.name, d.description, d.is_active, d.created_at, d.updated_at
         ORDER BY d.name ASC, d.id ASC""",
        (organization_id,),
    )
    return cursor.fetchall() or []


def get_department(conn: Any, organization_id: int, department_id: int) -> Optional[dict[str, Any]]:
    cursor = conn.cursor()
    cursor.execute(
        """SELECT d.id, d.organization_id, d.name, d.description, d.is_active,
                  d.created_at, d.updated_at,
                  COUNT(CASE WHEN sd.is_active=TRUE THEN sd.id END) AS member_count
             FROM departments d
        LEFT JOIN staff_destinations sd ON sd.organization_id=d.organization_id AND LOWER(TRIM(sd.department))=LOWER(TRIM(d.name))
            WHERE d.id=%s AND d.organization_id=%s
         GROUP BY d.id, d.organization_id, d.name, d.description, d.is_active, d.created_at, d.updated_at""",
        (department_id, organization_id),
    )
    return cursor.fetchone()


def create_department(conn: Any, organization_id: int, values: dict[str, Any]) -> dict[str, Any]:
    cursor = conn.cursor()
    name = values["name"].strip()
    description = (values.get("description") or "").strip() or None
    is_active = values.get("is_active", True)
    cursor.execute(
        """INSERT INTO departments (organization_id, name, description, is_active)
           VALUES (%s, %s, %s, %s)""",
        (organization_id, name, description, is_active),
    )
    dept_id = int(cursor.lastrowid)
    conn.commit()
    return get_department(conn, organization_id, dept_id)  # type: ignore[return-value]


def update_department(
    conn: Any, organization_id: int, department_id: int, changes: dict[str, Any],
) -> Optional[dict[str, Any]]:
    existing = get_department(conn, organization_id, department_id)
    if not existing:
        return None
    allowed = {"name", "description", "is_active"}
    fields, params = [], []
    new_name = None
    for name, value in changes.items():
        if name not in allowed:
            continue
        fields.append(f"{name}=%s")
        val = value.strip() or None if isinstance(value, str) else value
        if name == "name":
            new_name = val
        params.append(val)
    if fields:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE departments SET {', '.join(fields)} WHERE id=%s AND organization_id=%s",
            params + [department_id, organization_id],
        )
        if new_name and new_name != existing["name"]:
            cursor.execute(
                "UPDATE staff_destinations SET department=%s WHERE organization_id=%s AND department=%s",
                (new_name, organization_id, existing["name"]),
            )
        conn.commit()
    return get_department(conn, organization_id, department_id)


def delete_department(conn: Any, organization_id: int, department_id: int) -> bool:
    dept = get_department(conn, organization_id, department_id)
    if not dept:
        return False
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE staff_destinations SET department=NULL WHERE organization_id=%s AND department=%s",
        (organization_id, dept["name"]),
    )
    cursor.execute(
        "DELETE FROM departments WHERE id=%s AND organization_id=%s",
        (department_id, organization_id),
    )
    conn.commit()
    return True


def list_destinations(conn: Any, organization_id: int, active_only: bool = False) -> list[dict[str, Any]]:
    cursor = conn.cursor()
    where = "organization_id=%s" + (" AND is_active=TRUE" if active_only else "")
    cursor.execute(
        f"SELECT * FROM staff_destinations WHERE {where} ORDER BY priority,name,id",
        (organization_id,),
    )
    return cursor.fetchall() or []


def create_destination(conn: Any, organization_id: int, values: dict[str, Any]) -> dict[str, Any]:
    cursor = conn.cursor()
    dept = (values.get("department") or "").strip() or None
    if dept:
        cursor.execute(
            "INSERT IGNORE INTO departments (organization_id, name) VALUES (%s, %s)",
            (organization_id, dept),
        )
    cursor.execute(
        """INSERT INTO staff_destinations
             (organization_id,name,phone_e164,department,priority,is_active)
           VALUES (%s,%s,%s,%s,%s,%s)""",
        (
            organization_id, values["name"].strip(), values["phone_e164"],
            dept,
            values.get("priority", 100), values.get("is_active", True),
        ),
    )
    destination_id = int(cursor.lastrowid)
    conn.commit()
    return get_destination(conn, organization_id, destination_id)  # type: ignore[return-value]



def get_destination(conn: Any, organization_id: int, destination_id: int) -> Optional[dict[str, Any]]:
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM staff_destinations WHERE id=%s AND organization_id=%s",
        (destination_id, organization_id),
    )
    return cursor.fetchone()


def update_destination(
    conn: Any, organization_id: int, destination_id: int, changes: dict[str, Any],
) -> Optional[dict[str, Any]]:
    if not get_destination(conn, organization_id, destination_id):
        return None
    allowed = {"name", "phone_e164", "department", "priority", "is_active"}
    fields, params = [], []
    for name, value in changes.items():
        if name not in allowed:
            continue
        fields.append(f"{name}=%s")
        params.append(value.strip() or None if isinstance(value, str) else value)
    if fields:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE staff_destinations SET {', '.join(fields)} WHERE id=%s AND organization_id=%s",
            params + [destination_id, organization_id],
        )
        conn.commit()
    return get_destination(conn, organization_id, destination_id)


def delete_destination(conn: Any, organization_id: int, destination_id: int) -> bool:
    if not get_destination(conn, organization_id, destination_id):
        return False
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM staff_destinations WHERE id=%s AND organization_id=%s",
        (destination_id, organization_id),
    )
    conn.commit()
    return True


def get_transfer(conn: Any, organization_id: int, transfer_id: int) -> Optional[dict[str, Any]]:
    cursor = conn.cursor()
    cursor.execute(
        _TRANSFER_SELECT + " WHERE ct.id=%s AND ct.organization_id=%s",
        (transfer_id, organization_id),
    )
    return cursor.fetchone()


def get_transfer_for_webhook(
    conn: Any, transfer_id: int, correlation_id: str,
) -> Optional[dict[str, Any]]:
    cursor = conn.cursor()
    cursor.execute(
        _TRANSFER_SELECT
        + " JOIN call_logs cl ON cl.id=ct.call_log_id AND cl.organization_id=ct.organization_id"
          " WHERE ct.id=%s AND cl.correlation_id=%s",
        (transfer_id, correlation_id),
    )
    return cursor.fetchone()


def list_call_transfers(conn: Any, organization_id: int, call_log_id: int) -> list[dict[str, Any]]:
    cursor = conn.cursor()
    cursor.execute(
        _TRANSFER_SELECT
        + " WHERE ct.organization_id=%s AND ct.call_log_id=%s ORDER BY ct.id DESC",
        (organization_id, call_log_id),
    )
    return cursor.fetchall() or []


def get_transfer_phone_numbers(
    conn: Any, organization_id: int, destination_id: int,
) -> list[str]:
    """Return all target E.164 phone numbers for simultaneous ringing.

    If the destination has an assigned department, all active staff in that
    department are returned, ensuring the entire department team rings simultaneously.
    The primary destination's phone number is always placed first.
    """
    dest = get_destination(conn, organization_id, destination_id)
    if not dest:
        return []
    primary = str(dest.get("phone_e164") or "")
    dept = (dest.get("department") or "").strip()
    if not dept:
        return [primary] if primary else []
    cursor = conn.cursor()
    cursor.execute(
        """SELECT phone_e164 FROM staff_destinations
            WHERE organization_id=%s AND LOWER(TRIM(department))=LOWER(TRIM(%s)) AND is_active=TRUE
            ORDER BY priority ASC, id ASC""",
        (organization_id, dept),
    )
    rows = cursor.fetchall() or []
    numbers: list[str] = [primary] if primary else []
    for r in rows:
        phone = str(r.get("phone_e164") or "")
        if phone and phone not in numbers:
            numbers.append(phone)
    return numbers


def prepare_transfer(
    conn: Any, *, organization_id: int, call_log_id: int,
    destination_id: Optional[int] = None, department: Optional[str] = None,
    actor_user_id: int, idempotency_key: str,
) -> dict[str, Any]:
    cursor = conn.cursor()
    cursor.execute(
        """SELECT id,provider_call_id,call_sid,status,call_status,correlation_id
             FROM call_logs WHERE id=%s AND organization_id=%s FOR UPDATE""",
        (call_log_id, organization_id),
    )
    call = cursor.fetchone()
    if not call:
        raise LookupError("Call log not found")
    status = str(call.get("call_status") or call.get("status") or "").lower()
    if status not in LIVE_STATUSES:
        raise ValueError("Only a live connected call can be transferred")
    provider_call_id = str(call.get("provider_call_id") or call.get("call_sid") or "")
    if not provider_call_id or not call.get("correlation_id"):
        raise ValueError("The active provider call is not bound yet")

    if not destination_id and department:
        cursor.execute(
            """SELECT id FROM staff_destinations
                WHERE organization_id=%s AND LOWER(TRIM(department))=LOWER(TRIM(%s)) AND is_active=TRUE
                ORDER BY priority ASC, id ASC LIMIT 1""",
            (organization_id, department.strip()),
        )
        found = cursor.fetchone()
        if not found:
            raise ValueError(f"No active staff destination found for department '{department}'")
        destination_id = int(found["id"])
    elif not destination_id:
        raise ValueError("Transfer destination is unavailable")

    destination = get_destination(conn, organization_id, destination_id)
    if not destination or not destination.get("is_active"):
        raise ValueError("Transfer destination is unavailable")
    cursor.execute(
        """SELECT id FROM call_transfers
            WHERE organization_id=%s AND call_log_id=%s
              AND status IN ('requested','provider_accepted','ringing','answered') LIMIT 1""",
        (organization_id, call_log_id),
    )
    active = cursor.fetchone()
    if active:
        return get_transfer(conn, organization_id, int(active["id"]))  # type: ignore[return-value]
    cursor.execute(
        """INSERT INTO call_transfers
             (organization_id,call_log_id,destination_id,status,provider_call_id,
              initiated_by_user_id,idempotency_key)
           VALUES (%s,%s,%s,'requested',%s,%s,%s)
           ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id)""",
        (
            organization_id, call_log_id, destination_id, provider_call_id,
            actor_user_id, idempotency_key,
        ),
    )
    transfer_id = int(cursor.lastrowid)
    cursor.execute(
        """INSERT INTO audit_logs
             (organization_id,actor_user_id,action,resource_type,resource_id,result,metadata_json)
           VALUES (%s,%s,'call_transfer_requested','call_transfer',%s,'success',%s)""",
        (organization_id, actor_user_id, str(transfer_id), json.dumps({"call_log_id": call_log_id, "destination_id": destination_id})),
    )
    conn.commit()
    return get_transfer(conn, organization_id, transfer_id)  # type: ignore[return-value]


def set_provider_accepted(conn: Any, organization_id: int, transfer_id: int) -> dict[str, Any]:
    cursor = conn.cursor()
    cursor.execute(
        """UPDATE call_transfers SET status='provider_accepted',failure_reason=NULL
            WHERE id=%s AND organization_id=%s AND status='requested'""",
        (transfer_id, organization_id),
    )
    conn.commit()
    return get_transfer(conn, organization_id, transfer_id)  # type: ignore[return-value]


def mark_failed(conn: Any, organization_id: int, transfer_id: int, reason: str) -> None:
    cursor = conn.cursor()
    cursor.execute(
        """UPDATE call_transfers SET status='failed',failure_reason=%s,completed_at=NOW()
            WHERE id=%s AND organization_id=%s AND status NOT IN ('completed','cancelled')""",
        (reason[:500], transfer_id, organization_id),
    )
    conn.commit()


def apply_dial_event(
    conn: Any, *, transfer_id: int, correlation_id: str, data: dict[str, Any], final: bool,
) -> Optional[dict[str, Any]]:
    transfer = get_transfer_for_webhook(conn, transfer_id, correlation_id)
    if not transfer:
        return None
    action = str(data.get("DialAction") or "").lower()
    dial_status = str(data.get("DialStatus") or data.get("DialBLegStatus") or "").lower()
    if action in {"answer", "connected"} or dial_status in {"answered", "in-progress", "connected"}:
        status = "answered"
    elif action == "hangup" or (final and dial_status == "completed"):
        status = "completed"
    elif final or dial_status in {"busy", "failed", "timeout", "no-answer", "cancel", "cancelled"}:
        status = "cancelled" if dial_status in {"cancel", "cancelled"} else "failed"
    else:
        status = "ringing"
    cursor = conn.cursor()
    cursor.execute(
        """UPDATE call_transfers SET status=%s,
             provider_bleg_id=COALESCE(%s,provider_bleg_id),
             answered_at=CASE WHEN %s='answered' THEN COALESCE(answered_at,NOW()) ELSE answered_at END,
             completed_at=CASE WHEN %s IN ('completed','failed','cancelled') THEN COALESCE(completed_at,NOW()) ELSE completed_at END,
             failure_reason=CASE WHEN %s IN ('failed','cancelled') THEN %s ELSE failure_reason END
           WHERE id=%s AND organization_id=%s""",
        (
            status, data.get("DialBLegUUID") or None, status, status, status,
            str(data.get("DialHangupCause") or data.get("DialBLegHangupCauseName") or dial_status)[:500] or None,
            transfer_id, transfer["organization_id"],
        ),
    )
    conn.commit()
    return get_transfer(conn, int(transfer["organization_id"]), transfer_id)
