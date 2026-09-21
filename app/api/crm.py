import json
import hashlib
import hmac
import uuid
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query
import httpx

from app.api.auth import current_admin
from app.database.db import get_db
from app.schemas.crm import CrmConnectionInput, CrmConnectionResponse, CrmOutboxResponse
from app.services import crm_outbox_service, tenant_credentials_service


router = APIRouter(prefix="/crm", tags=["CRM"], dependencies=[Depends(current_admin)])


def _connection_response(row, credentials=None):
    if not row:
        return CrmConnectionResponse(configured=False)
    try:
        mapping = json.loads(row.get("field_mapping_json") or "{}")
    except Exception:
        mapping = {}
    host = urlparse((credentials or {}).get("webhook_url") or "").hostname
    return CrmConnectionResponse(
        configured=bool(credentials), id=row["id"], provider=row["provider"],
        name=row["name"], endpoint_host=host, is_active=bool(row["is_active"]),
        field_mapping=mapping, last_tested_at=row.get("last_tested_at"),
        last_test_status=row.get("last_test_status"), updated_at=row.get("updated_at"),
    )


@router.get("/connection", response_model=CrmConnectionResponse)
def read_connection(admin=Depends(current_admin), db=Depends(get_db)):
    row = crm_outbox_service.get_active_connection(db, admin["organization_id"])
    credentials = tenant_credentials_service.resolve_crm_webhook(db, admin["organization_id"])
    return _connection_response(row, credentials)


@router.put("/connection", response_model=CrmConnectionResponse)
def save_connection(
    value: CrmConnectionInput, admin=Depends(current_admin), db=Depends(get_db),
):
    organization_id = admin["organization_id"]
    tenant_credentials_service.set_credential(
        db, organization_id, "crm_webhook",
        {"webhook_url": value.webhook_url, "signing_secret": value.signing_secret},
        commit=False,
    )
    cursor = db.cursor()
    cursor.execute(
        """INSERT INTO crm_connections
             (organization_id,provider,name,is_active,field_mapping_json)
           VALUES (%s,'webhook',%s,%s,%s)
           ON DUPLICATE KEY UPDATE name=VALUES(name),is_active=VALUES(is_active),
             field_mapping_json=VALUES(field_mapping_json),updated_at=CURRENT_TIMESTAMP""",
        (organization_id, value.name.strip(), value.is_active, json.dumps(value.field_mapping)),
    )
    cursor.execute("SELECT id FROM crm_connections WHERE organization_id=%s AND provider='webhook'", (organization_id,))
    connection_id = int(cursor.fetchone()["id"])
    cursor.execute(
        """INSERT INTO audit_logs
             (organization_id,actor_user_id,action,resource_type,resource_id,result)
           VALUES (%s,%s,'crm_connection_updated','crm_connection',%s,'success')""",
        (organization_id, admin["id"], str(connection_id)),
    )
    db.commit()
    if value.is_active:
        crm_outbox_service.activate_waiting_events(db, organization_id, connection_id)
    row = crm_outbox_service.get_active_connection(db, organization_id)
    return _connection_response(row, {"webhook_url": value.webhook_url})


@router.delete("/connection")
def disable_connection(admin=Depends(current_admin), db=Depends(get_db)):
    organization_id = admin["organization_id"]
    cursor = db.cursor()
    cursor.execute(
        "UPDATE crm_connections SET is_active=FALSE WHERE organization_id=%s AND provider='webhook'",
        (organization_id,),
    )
    cursor.execute(
        """INSERT INTO audit_logs
             (organization_id,actor_user_id,action,resource_type,result)
           VALUES (%s,%s,'crm_connection_disabled','crm_connection','success')""",
        (organization_id, admin["id"]),
    )
    tenant_credentials_service.delete_credential(
        db, organization_id, "crm_webhook", commit=False,
    )
    db.commit()
    return {"status": "disabled"}


@router.post("/connection/test")
def test_connection(admin=Depends(current_admin), db=Depends(get_db)):
    """Send a signed, PII-free probe to the currently stored endpoint."""
    organization_id = int(admin["organization_id"])
    row = crm_outbox_service.get_active_connection(db, organization_id)
    credentials = tenant_credentials_service.resolve_crm_webhook(db, organization_id)
    if not row or not credentials:
        raise HTTPException(409, "Configure and enable the CRM connection first")
    event_id = f"test-{uuid.uuid4().hex}"
    payload = json.dumps(
        {"event_type": "connection_test", "event_id": event_id, "data": {"status": "probe"}},
        separators=(",", ":"),
    )
    signature = hmac.new(
        credentials["signing_secret"].encode(), payload.encode(), hashlib.sha256,
    ).hexdigest()
    response_status = None
    try:
        from app.workers.crm_delivery_worker import _assert_public_destination
        _assert_public_destination(credentials["webhook_url"])
        with httpx.Client(timeout=httpx.Timeout(15.0, connect=5.0), follow_redirects=False) as client:
            response = client.post(
                credentials["webhook_url"], content=payload.encode(), headers={
                    "Content-Type": "application/json",
                    "X-DigiDARA-Event": "connection_test",
                    "X-DigiDARA-Event-ID": event_id,
                    "X-DigiDARA-Idempotency-Key": event_id,
                    "X-DigiDARA-Signature": f"sha256={signature}",
                },
            )
        response_status = response.status_code
        if not 200 <= response.status_code < 300:
            raise RuntimeError(f"CRM webhook returned HTTP {response.status_code}")
    except Exception as exc:
        cursor = db.cursor()
        cursor.execute(
            "UPDATE crm_connections SET last_tested_at=NOW(),last_test_status='failed' WHERE id=%s AND organization_id=%s",
            (row["id"], organization_id),
        )
        db.commit()
        raise HTTPException(502, f"CRM connection test failed: {type(exc).__name__}") from exc
    cursor = db.cursor()
    cursor.execute(
        "UPDATE crm_connections SET last_tested_at=NOW(),last_test_status='success' WHERE id=%s AND organization_id=%s",
        (row["id"], organization_id),
    )
    cursor.execute(
        """INSERT INTO audit_logs
             (organization_id,actor_user_id,action,resource_type,resource_id,result)
           VALUES (%s,%s,'crm_connection_tested','crm_connection',%s,'success')""",
        (organization_id, admin["id"], str(row["id"])),
    )
    db.commit()
    return {"status": "success", "response_status": response_status}


@router.get("/events", response_model=list[CrmOutboxResponse])
def read_events(
    status: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=500),
    skip: int = Query(default=0, ge=0),
    admin=Depends(current_admin), db=Depends(get_db),
):
    return crm_outbox_service.list_events(
        db, admin["organization_id"], status=status, limit=limit, skip=skip,
    )


@router.post("/events/{event_id}/retry")
def retry_event(event_id: int, admin=Depends(current_admin), db=Depends(get_db)):
    try:
        updated = crm_outbox_service.requeue_event(db, admin["organization_id"], event_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail="Retryable CRM event not found")
    return {"status": "pending", "event_id": event_id}
