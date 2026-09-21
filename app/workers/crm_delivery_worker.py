"""Run with: python -m app.workers.crm_delivery_worker"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import socket
import time
import uuid
import ipaddress
from urllib.parse import urlparse

import httpx

from app.database.db import get_db_connection
from app.services import crm_outbox_service, tenant_credentials_service, runtime_readiness_service


WORKER_ID = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def _assert_public_destination(url: str) -> None:
    host = urlparse(url).hostname
    if not host:
        raise ValueError("CRM webhook has no hostname")
    addresses = {
        item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    }
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ValueError("CRM webhook resolved to a non-public address")


def deliver_event(db, event: dict) -> None:
    event_id = int(event["id"])
    credentials = tenant_credentials_service.resolve_crm_webhook(db, int(event["organization_id"]))
    if not credentials or not event.get("is_active"):
        crm_outbox_service.mark_failed(
            db, event_id, error="CRM connection is unavailable", response_status=None, retryable=True,
        )
        return
    payload = event["payload_json"]
    if not isinstance(payload, str):
        payload = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    signature = hmac.new(
        credentials["signing_secret"].encode(), payload.encode(), hashlib.sha256,
    ).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "X-DigiDARA-Event": event["event_type"],
        "X-DigiDARA-Event-ID": str(event_id),
        "X-DigiDARA-Idempotency-Key": event["idempotency_key"],
        "X-DigiDARA-Signature": f"sha256={signature}",
    }
    try:
        _assert_public_destination(credentials["webhook_url"])
        with httpx.Client(timeout=httpx.Timeout(15.0, connect=5.0), follow_redirects=False) as client:
            response = client.post(credentials["webhook_url"], content=payload.encode(), headers=headers)
        if 200 <= response.status_code < 300:
            crm_outbox_service.mark_delivered(db, event_id, response.status_code)
            return
        retryable = response.status_code in {408, 425, 429} or response.status_code >= 500
        crm_outbox_service.mark_failed(
            db, event_id, error=f"CRM webhook returned HTTP {response.status_code}",
            response_status=response.status_code, retryable=retryable,
        )
    except ValueError as exc:
        # Invalid/private destinations are configuration errors, not transient
        # delivery failures. Dead-letter immediately until an admin fixes them.
        crm_outbox_service.mark_failed(
            db, event_id, error=f"CRM webhook rejected: {type(exc).__name__}",
            response_status=None, retryable=False,
        )
    except (httpx.TimeoutException, httpx.NetworkError, OSError) as exc:
        crm_outbox_service.mark_failed(
            db, event_id, error=f"CRM webhook network failure: {type(exc).__name__}",
            response_status=None, retryable=True,
        )


def run_once(limit: int = 20) -> int:
    db = get_db_connection()
    try:
        runtime_readiness_service.record_worker_heartbeat(db, "crm_delivery", WORKER_ID)
        crm_outbox_service.recover_stale_locks(db)
        events = crm_outbox_service.claim_batch(db, worker_id=WORKER_ID, limit=limit)
        for event in events:
            deliver_event(db, event)
        return len(events)
    finally:
        db.close()


def main() -> None:
    poll_seconds = max(1.0, min(float(os.getenv("CRM_WORKER_POLL_SECONDS", "5")), 60.0))
    batch_size = max(1, min(int(os.getenv("CRM_WORKER_BATCH_SIZE", "20")), 100))
    while True:
        try:
            processed = run_once(batch_size)
        except Exception as exc:
            print(f"[CRM worker] cycle failed: {type(exc).__name__}")
            processed = 0
        time.sleep(0.25 if processed else poll_seconds)


if __name__ == "__main__":
    main()
