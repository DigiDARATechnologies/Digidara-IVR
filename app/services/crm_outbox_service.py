"""Durable canonical CRM events and retry-safe delivery state."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def get_active_connection(conn: Any, organization_id: int) -> Optional[dict[str, Any]]:
    cursor = conn.cursor()
    cursor.execute(
        """SELECT id,organization_id,provider,name,is_active,field_mapping_json,
                  last_tested_at,last_test_status,updated_at
             FROM crm_connections
            WHERE organization_id=%s AND is_active=TRUE
            ORDER BY id DESC LIMIT 1""",
        (organization_id,),
    )
    return cursor.fetchone()


def emit_event(
    conn: Any,
    *,
    organization_id: int,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    payload: dict[str, Any],
    idempotency_key: str,
    commit: bool = True,
) -> int:
    """Emitting with an idempotency_key already in the outbox supersedes
    that row: the new payload replaces the old one and delivery state
    resets so it goes out again. This is what lets a corrected event (e.g.
    a call re-scored from its full recording after an initial rushed
    analysis) actually reach a CRM that already received the first,
    less-accurate version -- a plain no-op duplicate would leave it stale.
    """
    connection = get_active_connection(conn, organization_id)
    status = "pending" if connection else "waiting_configuration"
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO crm_outbox
             (organization_id,connection_id,event_type,aggregate_type,aggregate_id,
              idempotency_key,payload_json,status,available_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NOW())
           ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id),
             connection_id=VALUES(connection_id),
             payload_json=VALUES(payload_json),
             status=VALUES(status),
             attempts=0,
             locked_at=NULL,
             locked_by=NULL,
             last_error=NULL,
             response_status=NULL,
             delivered_at=NULL,
             available_at=NOW(),
             updated_at=CURRENT_TIMESTAMP""",
        (
            organization_id, (connection or {}).get("id"), event_type[:80],
            aggregate_type[:80], str(aggregate_id)[:100], idempotency_key[:191],
            _json(payload), status,
        ),
    )
    event_id = int(cursor.lastrowid)
    if commit:
        conn.commit()
    return event_id


def emit_call_completed(conn: Any, call_log: dict[str, Any], *, commit: bool = True) -> int:
    call_id = int(call_log["id"])
    organization_id = int(call_log["organization_id"])
    cursor = conn.cursor()
    cursor.execute(
        """SELECT c.id,c.name,c.phone,c.email,c.language
             FROM customers c WHERE c.id=%s AND c.organization_id=%s""",
        (call_log["customer_id"], organization_id),
    )
    customer = cursor.fetchone() or {}
    payload = {
        "event_version": 1,
        "event_type": "call_completed",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "organization_id": organization_id,
        "call": {
            "id": call_id,
            "provider": call_log.get("provider"),
            "provider_call_id": call_log.get("provider_call_id") or call_log.get("call_sid"),
            "direction": call_log.get("call_direction"),
            "status": call_log.get("call_status") or call_log.get("status"),
            "duration_seconds": call_log.get("duration") or 0,
            "language": call_log.get("language"),
            "summary": call_log.get("summary"),
            "lead_score": call_log.get("lead_score"),
            "lead_status": call_log.get("lead_status"),
            "qualification": call_log.get("qualification"),
            "followup_required": bool(call_log.get("followup_required")),
            "followup_date": call_log.get("followup_date"),
        },
        "customer": {
            "id": customer.get("id"), "name": customer.get("name"),
            "phone": customer.get("phone"), "email": customer.get("email"),
            "language": customer.get("language"),
        },
    }
    return emit_event(
        conn, organization_id=organization_id, event_type="call_completed",
        aggregate_type="call_log", aggregate_id=str(call_id), payload=payload,
        idempotency_key=f"call_completed:v1:{call_id}",
        commit=commit,
    )


def emit_callback_required(conn: Any, callback: dict[str, Any], *, commit: bool = True) -> int:
    callback_id = int(callback["id"])
    payload = {
        "event_version": 1,
        "event_type": "callback_required",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "organization_id": int(callback["organization_id"]),
        "callback": {
            "id": callback_id,
            "customer_id": callback["customer_id"],
            "source_call_log_id": callback.get("source_call_log_id"),
            "requested_date": callback.get("requested_date"),
            "status": callback.get("status"),
        },
    }
    return emit_event(
        conn, organization_id=int(callback["organization_id"]),
        event_type="callback_required", aggregate_type="followup_reminder",
        aggregate_id=str(callback_id), payload=payload,
        idempotency_key=f"callback_required:v1:{callback_id}",
        commit=commit,
    )


def list_events(
    conn: Any, organization_id: int, *, status: Optional[str] = None,
    limit: int = 100, skip: int = 0,
) -> list[dict[str, Any]]:
    where = "organization_id=%s"
    params: list[Any] = [organization_id]
    if status:
        where += " AND status=%s"
        params.append(status)
    cursor = conn.cursor()
    cursor.execute(
        """SELECT id,event_type,aggregate_type,aggregate_id,status,attempts,max_attempts,
                  available_at,delivered_at,last_error,response_status,created_at,updated_at
             FROM crm_outbox WHERE """ + where + " ORDER BY id DESC LIMIT %s OFFSET %s",
        params + [limit, skip],
    )
    return cursor.fetchall() or []


def requeue_event(conn: Any, organization_id: int, event_id: int) -> bool:
    connection = get_active_connection(conn, organization_id)
    if not connection:
        raise ValueError("Configure and activate a CRM connection before retrying")
    cursor = conn.cursor()
    cursor.execute(
        """UPDATE crm_outbox
              SET status='pending',connection_id=%s,attempts=0,available_at=NOW(),
                  locked_at=NULL,locked_by=NULL,last_error=NULL
            WHERE id=%s AND organization_id=%s
              AND status IN ('failed','dead','waiting_configuration')""",
        (connection["id"], event_id, organization_id),
    )
    conn.commit()
    return cursor.rowcount == 1


def activate_waiting_events(conn: Any, organization_id: int, connection_id: int) -> int:
    cursor = conn.cursor()
    cursor.execute(
        """UPDATE crm_outbox SET status='pending',connection_id=%s,available_at=NOW()
            WHERE organization_id=%s AND status='waiting_configuration'""",
        (connection_id, organization_id),
    )
    count = cursor.rowcount
    conn.commit()
    return count


def claim_batch(conn: Any, *, worker_id: Optional[str] = None, limit: int = 20) -> list[dict[str, Any]]:
    worker_id = worker_id or str(uuid.uuid4())
    cursor = conn.cursor()
    cursor.execute("START TRANSACTION")
    cursor.execute(
        """SELECT id FROM crm_outbox
            WHERE status='pending' AND available_at<=NOW()
            ORDER BY id LIMIT %s FOR UPDATE SKIP LOCKED""",
        (limit,),
    )
    ids = [int(row["id"]) for row in (cursor.fetchall() or [])]
    if not ids:
        conn.commit()
        return []
    placeholders = ",".join(["%s"] * len(ids))
    cursor.execute(
        f"UPDATE crm_outbox SET status='processing',locked_at=NOW(),locked_by=%s "
        f"WHERE id IN ({placeholders})",
        [worker_id] + ids,
    )
    conn.commit()
    cursor.execute(
        f"""SELECT o.*,c.provider,c.is_active
              FROM crm_outbox o JOIN crm_connections c ON c.id=o.connection_id
             WHERE o.id IN ({placeholders}) AND o.locked_by=%s ORDER BY o.id""",
        ids + [worker_id],
    )
    return cursor.fetchall() or []


def recover_stale_locks(conn: Any, stale_minutes: int = 10) -> int:
    cursor = conn.cursor()
    cursor.execute(
        """UPDATE crm_outbox SET status='pending',locked_at=NULL,locked_by=NULL,
                  last_error='Recovered stale worker lock'
            WHERE status='processing' AND locked_at < NOW() - INTERVAL %s MINUTE""",
        (stale_minutes,),
    )
    count = cursor.rowcount
    conn.commit()
    return count


def mark_delivered(conn: Any, event_id: int, response_status: int) -> None:
    cursor = conn.cursor()
    cursor.execute(
        """UPDATE crm_outbox SET status='delivered',attempts=attempts+1,
                  response_status=%s,delivered_at=NOW(),last_error=NULL,
                  locked_at=NULL,locked_by=NULL WHERE id=%s""",
        (response_status, event_id),
    )
    conn.commit()


def mark_failed(
    conn: Any, event_id: int, *, error: str, response_status: Optional[int], retryable: bool,
) -> None:
    cursor = conn.cursor()
    cursor.execute("SELECT attempts,max_attempts FROM crm_outbox WHERE id=%s", (event_id,))
    row = cursor.fetchone() or {"attempts": 0, "max_attempts": 8}
    attempts = int(row["attempts"]) + 1
    exhausted = attempts >= int(row["max_attempts"])
    next_status = "dead" if exhausted or not retryable else "pending"
    delay_seconds = min(3600, 30 * (2 ** min(attempts - 1, 7)))
    cursor.execute(
        """UPDATE crm_outbox SET status=%s,attempts=%s,response_status=%s,
                  last_error=%s,available_at=DATE_ADD(NOW(),INTERVAL %s SECOND),
                  locked_at=NULL,locked_by=NULL WHERE id=%s""",
        (next_status, attempts, response_status, error[:1000], delay_seconds, event_id),
    )
    conn.commit()
