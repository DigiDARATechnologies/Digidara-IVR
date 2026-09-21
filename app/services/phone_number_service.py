"""DID -> tenant/campaign routing for inbound Plivo calls.

Replaces the old single global ``PLIVO_INBOUND_CAMPAIGN_ID`` env var: every
Plivo number a business owns is registered here against the organization
(and the inbound campaign) it should route to, so multiple tenants can each
receive inbound calls on their own dedicated number.
"""

import re
from typing import Any, Dict, List, Optional

from app.schemas.phone_number import PhoneNumberCreate, PhoneNumberUpdate

_SELECT_COLUMNS = (
    "id, organization_id, campaign_id, plivo_number, label, is_active, created_at"
)


def normalize_number(value: str) -> str:
    """Strip everything but digits so '+91 80-4123-4567' and '918041234567'
    are treated as the same DID for lookup and storage."""
    return re.sub(r"\D", "", value or "")


def row_to_dict(row: Any) -> Dict[str, Any]:
    return dict(row) if row else {}


def get_by_id(conn: Any, phone_number_id: int, organization_id: int) -> Optional[Dict[str, Any]]:
    cursor = conn.cursor()
    cursor.execute(
        f"SELECT {_SELECT_COLUMNS} FROM phone_numbers WHERE id=%s AND organization_id=%s",
        (phone_number_id, organization_id),
    )
    return row_to_dict(cursor.fetchone()) or None


def list_for_organization(conn: Any, organization_id: int) -> List[Dict[str, Any]]:
    cursor = conn.cursor()
    cursor.execute(
        f"SELECT {_SELECT_COLUMNS} FROM phone_numbers WHERE organization_id=%s ORDER BY id DESC",
        (organization_id,),
    )
    return [row_to_dict(row) for row in cursor.fetchall()]


def get_active_route_for_number(conn: Any, plivo_number: str) -> Optional[Dict[str, Any]]:
    """The lookup the inbound Plivo webhook uses: given the dialed DID
    (Plivo's ``To`` field), find which organization/campaign owns it."""
    normalized = normalize_number(plivo_number)
    if not normalized:
        return None
    cursor = conn.cursor()
    cursor.execute(
        f"SELECT {_SELECT_COLUMNS} FROM phone_numbers "
        "WHERE plivo_number=%s AND is_active=TRUE LIMIT 1",
        (normalized,),
    )
    return row_to_dict(cursor.fetchone()) or None


def create(
    conn: Any, organization_id: int, phone_number_in: PhoneNumberCreate,
) -> Dict[str, Any]:
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO phone_numbers (organization_id, campaign_id, plivo_number, label, is_active) "
        "VALUES (%s, %s, %s, %s, %s)",
        (
            organization_id, phone_number_in.campaign_id, phone_number_in.plivo_number,
            phone_number_in.label, phone_number_in.is_active,
        ),
    )
    conn.commit()
    new_id = cursor.lastrowid
    return get_by_id(conn, new_id, organization_id)


def update(
    conn: Any, phone_number_id: int, organization_id: int, phone_number_in: PhoneNumberUpdate,
) -> Optional[Dict[str, Any]]:
    existing = get_by_id(conn, phone_number_id, organization_id)
    if not existing:
        return None

    update_data = phone_number_in.model_dump(exclude_unset=True)
    if not update_data:
        return existing

    fields = [f"{key} = %s" for key in update_data]
    values = list(update_data.values())
    values.extend((phone_number_id, organization_id))
    cursor = conn.cursor()
    cursor.execute(
        f"UPDATE phone_numbers SET {', '.join(fields)} WHERE id = %s AND organization_id = %s",
        tuple(values),
    )
    conn.commit()
    return get_by_id(conn, phone_number_id, organization_id)


def delete(conn: Any, phone_number_id: int, organization_id: int) -> bool:
    existing = get_by_id(conn, phone_number_id, organization_id)
    if not existing:
        return False
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM phone_numbers WHERE id = %s AND organization_id = %s",
        (phone_number_id, organization_id),
    )
    conn.commit()
    return True
