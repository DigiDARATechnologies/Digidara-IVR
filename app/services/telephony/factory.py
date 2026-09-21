import os
from typing import Any, Optional

from .base import TelephonyProvider
from .plivo_provider import PlivoProvider


def get_telephony_provider(
    db: Any = None, organization_id: Optional[int] = None,
) -> TelephonyProvider:
    """Build the configured telephony provider.

    Pass db + organization_id to resolve that tenant's own stored Plivo
    credentials (falling back to the shared .env values if it has none
    configured). Called with no arguments, this always uses the shared
    .env credentials — the correct behavior for any caller that doesn't
    yet have tenant context available.
    """
    provider = (os.getenv("TELEPHONY_PROVIDER") or "plivo").strip().lower()
    if provider != "plivo":
        raise RuntimeError(
            f"Unsupported TELEPHONY_PROVIDER={provider!r}; this release supports 'plivo'."
        )
    if db is not None and organization_id is not None:
        from app.services.tenant_credentials_service import resolve_plivo_credentials

        creds = resolve_plivo_credentials(db, organization_id)
        return PlivoProvider(
            auth_id=creds.get("auth_id"),
            auth_token=creds.get("auth_token"),
            from_number=creds.get("from_number"),
        )
    return PlivoProvider()
