"""Automated Plivo India number provisioning.

The flow: an organization submits its business KYC documents through our own
UI; this module submits them to Plivo's Compliance API on DigiDARA's main
account. Once Plivo approves the application (delivered via webhook), the
organization picks a specific number from a trust-tier prefix (080/022 today;
160 pending confirmation with Plivo — see TECHNICAL_DEBT.md), we buy that
exact number under the approved application, create an isolated Plivo
subaccount for the organization if it doesn't have one yet, and move the
number into it. The subaccount's resulting Auth ID/Token are stored through
the existing tenant_credentials_service, so the organization's calls resolve
to their own dedicated Plivo identity with no further manual setup.

DigiDARA's own main account credentials (PLIVO_AUTH_ID/PLIVO_AUTH_TOKEN) are
used for every call in this module — a tenant has no Plivo account of its own
until this flow completes, so there is nothing tenant-specific to resolve
credentials from yet.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

import plivo

from app.services import tenant_credentials_service

# STD-code prefixes chosen for caller recognizability/answer-rate, not
# geography. 160 is a known TRAI-mandated business-caller series but is
# intentionally left out until its exact Search API parameters are confirmed
# with Plivo directly.
PREFIX_CITY_MAP = {
    "080": "Bangalore",
    "022": "Mumbai",
}


class ProvisioningError(Exception):
    """A Plivo provisioning step failed in a way the caller should see."""


def _main_account_client() -> plivo.RestClient:
    auth_id = (os.getenv("PLIVO_AUTH_ID") or "").strip()
    auth_token = (os.getenv("PLIVO_AUTH_TOKEN") or "").strip()
    if not auth_id or not auth_token:
        raise ProvisioningError("PLIVO_AUTH_ID/PLIVO_AUTH_TOKEN are not configured")
    return plivo.RestClient(auth_id=auth_id, auth_token=auth_token)


def _as_dict(response: Any) -> dict:
    """Plivo SDK responses are attribute-access objects, not plain dicts."""
    try:
        return dict(vars(response))
    except TypeError:
        return {"value": response}


def get_compliance_requirements(country_iso: str = "IN", number_type: str = "local") -> dict:
    """Return the document types/fields Plivo requires for this country/number type."""
    client = _main_account_client()
    response = client.phone_number_compliance_requirements.get(
        country_iso=country_iso, number_type=number_type, user_type="business",
    )
    return _as_dict(response)


def submit_compliance_application(
    db, organization_id: int, *,
    business_name: str, business_email: str, address_line1: str, city: str,
    state: str, postal_code: str, registration_number: str,
    document_type_ids: list[str], document_paths: list[str], callback_url: str,
    country_iso: str = "IN", number_type: str = "local",
) -> dict:
    """Submit a customer's KYC documents to Plivo on their behalf and record the application."""
    if len(document_type_ids) != len(document_paths):
        raise ValueError("document_type_ids and document_paths must be the same length")
    client = _main_account_client()
    documents = [
        {"document_type_id": doc_type_id, "data_fields": {"business_name": business_name}}
        for doc_type_id in document_type_ids
    ]
    data = {
        "country_iso": country_iso,
        "number_type": number_type,
        "alias": f"org-{organization_id}-compliance",
        "end_user": {
            "type": "business",
            "name": business_name,
            "email": business_email,
            "address_line1": address_line1,
            "city": city,
            "state": state,
            "postal_code": postal_code,
            "country": country_iso,
            "registration_number": registration_number,
        },
        "documents": documents,
        "callback_url": callback_url,
        "callback_method": "POST",
    }
    try:
        response = client.phone_number_compliance.create(data=data, documents=document_paths)
    except Exception as exc:
        raise ProvisioningError(f"Plivo rejected the compliance application: {exc}") from exc

    payload = _as_dict(response)
    compliance_id = payload.get("compliance_id") or payload.get("id")

    cursor = db.cursor()
    cursor.execute(
        """INSERT INTO plivo_compliance_applications
               (organization_id, plivo_compliance_id, status, country_iso, number_type,
                business_name, business_email, raw_response)
           VALUES (%s,%s,'pending',%s,%s,%s,%s,%s)""",
        (
            organization_id, compliance_id, country_iso, number_type,
            business_name, business_email, json.dumps(payload, default=str),
        ),
    )
    db.commit()
    return payload


def handle_compliance_webhook(db, payload: dict) -> Optional[dict]:
    """Update our stored application's status from Plivo's compliance callback."""
    compliance_id = payload.get("compliance_id") or payload.get("id")
    status_value = (payload.get("status") or "").strip().lower()
    if not compliance_id or not status_value:
        return None
    cursor = db.cursor()
    cursor.execute(
        """UPDATE plivo_compliance_applications
           SET status=%s, raw_response=%s
           WHERE plivo_compliance_id=%s""",
        (status_value, json.dumps(payload, default=str), compliance_id),
    )
    db.commit()
    cursor.execute(
        "SELECT * FROM plivo_compliance_applications WHERE plivo_compliance_id=%s",
        (compliance_id,),
    )
    return cursor.fetchone()


def get_latest_application(db, organization_id: int) -> Optional[dict]:
    cursor = db.cursor()
    cursor.execute(
        """SELECT * FROM plivo_compliance_applications
           WHERE organization_id=%s ORDER BY id DESC LIMIT 1""",
        (organization_id,),
    )
    return cursor.fetchone()


def search_numbers(prefix: str, limit: int = 10) -> list[dict]:
    """Search available India numbers for a trust-tier prefix (080/022 today)."""
    city = PREFIX_CITY_MAP.get(prefix)
    if not city:
        raise ProvisioningError(
            f"Unsupported number prefix {prefix!r}; supported: {sorted(PREFIX_CITY_MAP)}"
        )
    client = _main_account_client()
    results = client.numbers.search(country_iso="IN", type="fixed", city=city, limit=limit)
    return [
        {
            "number": n.number,
            "city": getattr(n, "city", None),
            "region": getattr(n, "region", None),
            "monthly_rental_rate": getattr(n, "monthly_rental_rate", None),
            "voice_rate": getattr(n, "voice_rate", None),
        }
        for n in results
    ]


def _ensure_subaccount(db, organization_id: int) -> dict:
    """Return this org's Plivo subaccount, creating one if it doesn't exist yet."""
    existing = tenant_credentials_service.get_credential(db, organization_id, "plivo")
    if existing and existing.get("auth_id") and existing.get("auth_token"):
        return existing

    client = _main_account_client()
    try:
        response = client.subaccounts.create(name=f"digidara-org-{organization_id}", enabled=True)
    except Exception as exc:
        raise ProvisioningError(f"Could not create a Plivo subaccount: {exc}") from exc
    payload = _as_dict(response)
    subaccount_auth_id = payload.get("auth_id")
    subaccount_auth_token = payload.get("auth_token")
    if not subaccount_auth_id or not subaccount_auth_token:
        raise ProvisioningError("Plivo did not return subaccount credentials")

    credentials = {"auth_id": subaccount_auth_id, "auth_token": subaccount_auth_token}
    tenant_credentials_service.set_credential(db, organization_id, "plivo", credentials)
    return credentials


def provision_number(db, organization_id: int, number: str, compliance_application_id: str) -> dict:
    """Buy a specific, customer-chosen number and hand it off to the org's subaccount.

    This is the one step in this module with a real, recurring cost — it
    should only ever run from an explicit, confirmed user action, never from
    a test or a background job.
    """
    subaccount = _ensure_subaccount(db, organization_id)
    client = _main_account_client()
    try:
        client.numbers.buy(number=number, compliance_application_id=compliance_application_id)
        client.numbers.update(number=number, subaccount=subaccount["auth_id"])
    except Exception as exc:
        raise ProvisioningError(f"Could not provision number {number}: {exc}") from exc

    cursor = db.cursor()
    cursor.execute(
        """UPDATE plivo_compliance_applications
           SET provisioned_number=%s, subaccount_auth_id=%s
           WHERE organization_id=%s AND plivo_compliance_id=%s""",
        (number, subaccount["auth_id"], organization_id, compliance_application_id),
    )
    db.commit()

    from_number = f"+{number}" if not number.startswith("+") else number
    existing = tenant_credentials_service.get_credential(db, organization_id, "plivo") or {}
    tenant_credentials_service.set_credential(db, organization_id, "plivo", {
        **existing, "from_number": from_number,
    })

    return {"number": number, "subaccount_auth_id": subaccount["auth_id"]}
