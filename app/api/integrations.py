"""Per-organization provider credential management (Integrations settings)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.auth import current_admin
from app.database.db import get_db
from app.services import tenant_credentials_service as creds

router = APIRouter(prefix="/integrations", tags=["Integrations"])


class CredentialInput(BaseModel):
    fields: dict[str, str]


@router.get("/credentials")
def list_credentials(admin=Depends(current_admin), db=Depends(get_db)):
    return creds.list_credential_status(db, admin["organization_id"])


@router.put("/credentials/{provider}")
def upsert_credential(
    provider: str, data: CredentialInput, admin=Depends(current_admin), db=Depends(get_db),
):
    try:
        creds.set_credential(db, admin["organization_id"], provider, data.fields)
    except creds.UnknownProviderError as exc:
        raise HTTPException(404, str(exc)) from exc
    except creds.CredentialEncryptionError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"message": f"{provider.capitalize()} credentials saved"}


@router.delete("/credentials/{provider}")
def remove_credential(provider: str, admin=Depends(current_admin), db=Depends(get_db)):
    creds.delete_credential(db, admin["organization_id"], provider)
    return {"message": f"{provider.capitalize()} credentials removed; using shared defaults"}
