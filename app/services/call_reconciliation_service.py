"""Recover provider calls whose terminal webhook never reached the backend."""

from __future__ import annotations

import datetime
from typing import Any

from app.services import call_log_service
from app.services.telephony import get_telephony_provider
from app.services.telephony.status import map_plivo_status


TERMINAL_CALL_STATUSES = {"completed", "busy", "no-answer", "canceled", "failed"}


def reconcile_unstarted_provider_calls(
    conn: Any,
    organization_id: int,
    *,
    provider: Any = None,
    minimum_age_seconds: int = 45,
    limit: int = 10,
) -> int:
    """Finalize answered calls that never established a provider media stream.

    The age guard avoids racing the normal answer -> DTMF -> stream startup path.
    Provider CDR state remains authoritative; a call is never finalized merely
    because it is old or because the local stream identifier is absent.
    """
    cutoff = datetime.datetime.now() - datetime.timedelta(
        seconds=max(30, min(int(minimum_age_seconds), 600))
    )
    cursor = conn.cursor()
    cursor.execute(
        """SELECT id,call_sid,provider_call_id
           FROM call_logs
           WHERE organization_id=%s AND provider='plivo'
             AND COALESCE(call_status,status) IN
                 ('initiated','ringing','answered','in-progress','ongoing')
             AND provider_call_id IS NOT NULL
             AND provider_stream_id IS NULL
             AND answered_at IS NOT NULL AND answered_at < %s
           ORDER BY id ASC LIMIT %s""",
        (organization_id, cutoff, max(1, min(int(limit), 50))),
    )
    candidates = cursor.fetchall()
    if not candidates:
        return 0

    telephony = provider or get_telephony_provider(conn, organization_id)
    reconciled = 0
    for log in candidates:
        call_id = str(log.get("provider_call_id") or log.get("call_sid") or "")
        if not call_id:
            continue
        try:
            details = telephony.get_call(call_id)
        except Exception as exc:
            print(
                "[Call reconciliation] provider lookup failed | "
                f"call={call_id} error={type(exc).__name__}"
            )
            continue

        hangup_cause = str((details.metadata or {}).get("hangup_cause") or "")
        status = map_plivo_status(details.status, hangup_cause)
        if status not in TERMINAL_CALL_STATUSES:
            continue

        failure_reason = hangup_cause or "Recovered terminal provider call"
        cursor.execute(
            """UPDATE call_logs SET provider_status=%s, failure_reason=%s,
               estimated_telephony_cost_usd=%s,
               provider_bill_duration_seconds=%s
               WHERE id=%s AND organization_id=%s""",
            (
                status,
                failure_reason,
                details.cost_usd,
                details.billed_duration_seconds,
                log["id"],
                organization_id,
            ),
        )
        conn.commit()
        call_log_service.finalize_call_log(
            conn,
            str(log.get("call_sid") or call_id),
            status,
            details.duration_seconds,
        )
        reconciled += 1
        print(
            "[Call reconciliation] recovered missed terminal callback | "
            f"call={call_id} status={status} cause={hangup_cause or 'unknown'}"
        )
    return reconciled
