"""Per-organization, encrypted provider credential storage.

Backs the "Integrations" settings page: each organization may optionally
store its own Plivo and OpenAI credentials, encrypted at rest with
DATA_ENCRYPTION_KEY. Every resolver in this module falls back to the
shared .env values when an organization has not configured its own, so a
tenant with no stored credentials keeps working exactly as before this
feature existed.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

from cryptography.fernet import Fernet

KEY_VERSION = "v1"
PROVIDERS = ("plivo", "openai", "crm_webhook")

PROVIDER_FIELDS = {
    "plivo": ("auth_id", "auth_token", "from_number"),
    "openai": ("api_key",),
    "crm_webhook": ("webhook_url", "signing_secret"),
}


class CredentialEncryptionError(Exception):
    """DATA_ENCRYPTION_KEY is missing or not a valid Fernet key."""


class UnknownProviderError(Exception):
    """The requested provider is not one this app stores tenant credentials for."""


def _fernet() -> Fernet:
    key = (os.getenv("DATA_ENCRYPTION_KEY") or "").strip()
    if not key:
        raise CredentialEncryptionError("DATA_ENCRYPTION_KEY is not configured")
    try:
        return Fernet(key.encode())
    except Exception as exc:
        raise CredentialEncryptionError("DATA_ENCRYPTION_KEY is not a valid Fernet key") from exc


def _last_four(fields: dict[str, str]) -> Optional[str]:
    for value in fields.values():
        if value:
            digits = value.strip()
            return digits[-4:] if len(digits) >= 4 else digits
    return None


def set_credential(
    db, organization_id: int, provider: str, fields: dict[str, str], *, commit: bool = True,
) -> None:
    """Encrypt and store (or replace) one provider's credential set for a tenant."""
    if provider not in PROVIDERS:
        raise UnknownProviderError(f"Unsupported provider: {provider!r}")
    allowed = PROVIDER_FIELDS[provider]
    clean = {key: (fields.get(key) or "").strip() for key in allowed}
    if not any(clean.values()):
        raise ValueError("At least one credential field must be provided")
    ciphertext = _fernet().encrypt(json.dumps(clean).encode()).decode()
    cursor = db.cursor()
    cursor.execute(
        """INSERT INTO api_credentials
               (organization_id, provider, credential_ciphertext, key_version, last_four, rotated_at)
           VALUES (%s, %s, %s, %s, %s, NOW())
           ON DUPLICATE KEY UPDATE
               credential_ciphertext=VALUES(credential_ciphertext),
               key_version=VALUES(key_version),
               last_four=VALUES(last_four),
               rotated_at=NOW()""",
        (organization_id, provider, ciphertext, KEY_VERSION, _last_four(clean)),
    )
    if commit:
        db.commit()


def get_credential(db, organization_id: int, provider: str) -> Optional[dict[str, str]]:
    """Return a tenant's decrypted credential fields, or None if not configured."""
    cursor = db.cursor()
    cursor.execute(
        "SELECT credential_ciphertext FROM api_credentials WHERE organization_id=%s AND provider=%s",
        (organization_id, provider),
    )
    row = cursor.fetchone()
    if not row:
        return None
    try:
        decrypted = _fernet().decrypt(row["credential_ciphertext"].encode())
        return json.loads(decrypted)
    except Exception:
        return None


def list_credential_status(db, organization_id: int) -> list[dict[str, Any]]:
    """Return masked status (never the plaintext) for every configured provider."""
    cursor = db.cursor()
    cursor.execute(
        """SELECT provider, last_four, rotated_at, updated_at
           FROM api_credentials WHERE organization_id=%s""",
        (organization_id,),
    )
    configured = {row["provider"]: row for row in cursor.fetchall()}
    return [
        {
            "provider": provider,
            "configured": provider in configured,
            "last_four": configured.get(provider, {}).get("last_four"),
            "rotated_at": str(configured[provider]["rotated_at"]) if provider in configured else None,
        }
        for provider in PROVIDERS
    ]


def delete_credential(
    db, organization_id: int, provider: str, *, commit: bool = True,
) -> None:
    """Remove a tenant's stored credential so it falls back to the shared .env again."""
    cursor = db.cursor()
    cursor.execute(
        "DELETE FROM api_credentials WHERE organization_id=%s AND provider=%s",
        (organization_id, provider),
    )
    if commit:
        db.commit()


def resolve_plivo_credentials(db, organization_id: Optional[int]) -> dict[str, Optional[str]]:
    """Per-tenant Plivo credentials if configured, else the shared .env values."""
    stored = get_credential(db, organization_id, "plivo") if organization_id else None
    return {
        "auth_id": (stored or {}).get("auth_id") or os.getenv("PLIVO_AUTH_ID"),
        "auth_token": (stored or {}).get("auth_token") or os.getenv("PLIVO_AUTH_TOKEN"),
        "from_number": (stored or {}).get("from_number") or os.getenv("PLIVO_FROM_NUMBER"),
    }


def resolve_openai_api_key(db, organization_id: Optional[int]) -> Optional[str]:
    """Per-tenant OpenAI API key if configured, else the shared .env value."""
    stored = get_credential(db, organization_id, "openai") if organization_id else None
    return (stored or {}).get("api_key") or os.getenv("OPENAI_API_KEY")


def resolve_crm_webhook(db, organization_id: int) -> Optional[dict[str, str]]:
    """Return a tenant CRM webhook configuration without any shared fallback."""
    stored = get_credential(db, organization_id, "crm_webhook")
    if not stored or not stored.get("webhook_url") or not stored.get("signing_secret"):
        return None
    return {
        "webhook_url": stored["webhook_url"],
        "signing_secret": stored["signing_secret"],
    }
