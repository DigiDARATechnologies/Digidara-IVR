"""Secret-safe runtime and production configuration checks."""

from __future__ import annotations

import os
from urllib.parse import urlparse


PLACEHOLDERS = {"", "your-public-host", "your_plivo_auth_id", "your_plivo_auth_token", "your_plivo_number"}


def _configured(name: str, minimum: int = 1) -> bool:
    value = (os.getenv(name) or "").strip()
    return value not in PLACEHOLDERS and len(value) >= minimum


def _public_https(value: str, *, scheme: str) -> bool:
    parsed = urlparse(value.strip())
    return bool(parsed.hostname and parsed.scheme == scheme and parsed.hostname not in {"localhost", "127.0.0.1"})


def configuration_checks() -> list[dict[str, str]]:
    production = (os.getenv("ENVIRONMENT") or "development").lower() == "production"
    webhook = (os.getenv("WEBHOOK_BASE_URL") or "").strip()
    stream = (os.getenv("PLIVO_STREAM_BASE_URL") or "").strip()
    cors = [item.strip() for item in (os.getenv("CORS_ALLOWED_ORIGINS") or "").split(",") if item.strip()]
    webhook_ok = _public_https(webhook, scheme="https") and (not production or "trycloudflare.com" not in webhook)
    stream_ok = _public_https(stream, scheme="wss") and (not production or "trycloudflare.com" not in stream)
    if webhook_ok and stream_ok:
        webhook_ok = urlparse(webhook).hostname == urlparse(stream).hostname
        stream_ok = webhook_ok
    cors_ok = bool(cors) and (not production or all(_public_https(item, scheme="https") for item in cors))
    return [
        {"name": "Environment", "status": "production" if production else "development"},
        {"name": "Plivo credentials", "status": "configured" if all(_configured(name) for name in ("PLIVO_AUTH_ID", "PLIVO_AUTH_TOKEN", "PLIVO_FROM_NUMBER")) else "action_required"},
        {"name": "OpenAI API key", "status": "configured" if _configured("OPENAI_API_KEY", 20) else "action_required"},
        {"name": "Public webhook and stream URLs", "status": "configured" if webhook_ok and stream_ok else "action_required"},
        {"name": "JWT signing secret", "status": "configured" if _configured("JWT_SECRET", 32) else "action_required"},
        {"name": "Credential encryption key", "status": "configured" if _configured("DATA_ENCRYPTION_KEY", 32) else "action_required"},
        {"name": "Plivo V3 signature validation", "status": "configured" if (os.getenv("PLIVO_VALIDATE_SIGNATURES", "true").lower() in {"1", "true", "yes", "on"}) else "action_required"},
        {"name": "Browser origin allow-list", "status": "configured" if cors_ok else "action_required"},
    ]


def worker_check(conn) -> dict[str, str]:
    cursor = conn.cursor()
    cursor.execute(
        """SELECT last_seen_at FROM runtime_worker_heartbeats
           WHERE worker_name='crm_delivery' ORDER BY last_seen_at DESC LIMIT 1"""
    )
    row = cursor.fetchone()
    if not row:
        return {"name": "CRM delivery worker", "status": "not_seen"}
    cursor.execute(
        """SELECT CASE WHEN last_seen_at >= DATE_SUB(NOW(), INTERVAL 90 SECOND)
                    THEN 'healthy' ELSE 'stale' END AS status
           FROM runtime_worker_heartbeats WHERE worker_name='crm_delivery'
           ORDER BY last_seen_at DESC LIMIT 1"""
    )
    result = cursor.fetchone() or {}
    return {"name": "CRM delivery worker", "status": result.get("status") or "stale"}


def record_worker_heartbeat(conn, worker_name: str, worker_id: str) -> None:
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO runtime_worker_heartbeats(worker_name,worker_id,last_seen_at)
           VALUES (%s,%s,NOW())
           ON DUPLICATE KEY UPDATE worker_id=VALUES(worker_id),last_seen_at=NOW()""",
        (worker_name, worker_id),
    )
    conn.commit()
