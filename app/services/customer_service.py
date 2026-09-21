import datetime
import re
from typing import List, Optional, Dict, Any
from app.schemas.customer import CustomerCreate, CustomerUpdate

def row_to_dict(row: Any) -> Dict[str, Any]:
    """Helper to convert a row object to a standard Python dictionary."""
    if not row:
        return {}
    d = dict(row)
    for key, val in d.items():
        if isinstance(val, (datetime.datetime, datetime.date)):
            d[key] = val.strftime("%Y-%m-%d %H:%M:%S")
    return d

def get_customer_by_id(
    conn: Any, customer_id: int, organization_id: int,
) -> Optional[Dict[str, Any]]:
    """Retrieves a single customer by their database ID."""
    cursor = conn.cursor()
    cursor.execute("SELECT id, organization_id, name, email, phone, language, investigated_course, internship_or_course, course_duration, created_at FROM customers WHERE id = %s AND organization_id = %s", (customer_id, organization_id))
    row = cursor.fetchone()
    if row:
        return row_to_dict(row)
    return None

def get_customer_by_email(
    conn: Any, email: str, organization_id: int,
) -> Optional[Dict[str, Any]]:
    """Retrieves a single customer by their email address."""
    cursor = conn.cursor()
    cursor.execute("SELECT id, organization_id, name, email, phone, language, investigated_course, internship_or_course, course_duration, created_at FROM customers WHERE email = %s AND organization_id = %s", (email, organization_id))
    row = cursor.fetchone()
    if row:
        return row_to_dict(row)
    return None

def get_all_customers(
    conn: Any, organization_id: int, skip: int = 0, limit: int = 100,
) -> List[Dict[str, Any]]:
    """Retrieves a list of all customers with pagination."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, organization_id, name, email, phone, language, investigated_course, internship_or_course, course_duration, created_at FROM customers WHERE organization_id=%s ORDER BY id DESC LIMIT %s OFFSET %s",
        (organization_id, limit, skip)
    )
    rows = cursor.fetchall()
    return [row_to_dict(row) for row in rows]

def create_customer(
    conn: Any, organization_id: int, customer_in: CustomerCreate,
) -> Dict[str, Any]:
    """Inserts a new customer. Raises pymysql.IntegrityError if email is a duplicate."""
    cursor = conn.cursor()
    data = customer_in.model_dump()
    fields = ["organization_id"]
    placeholders = ["%s"]
    values = [organization_id]
    for k, v in data.items():
        fields.append(k)
        placeholders.append("%s")
        values.append(v)
    query = f"INSERT INTO customers ({', '.join(fields)}) VALUES ({', '.join(placeholders)})"
    cursor.execute(query, tuple(values))
    conn.commit()
    new_id = cursor.lastrowid
    
    # Retrieve and return the created customer
    return get_customer_by_id(conn, new_id, organization_id)

def update_customer(
    conn: Any, customer_id: int, organization_id: int, customer_in: CustomerUpdate,
) -> Optional[Dict[str, Any]]:
    """Updates selected fields of an existing customer."""
    # Check if the customer exists first
    existing = get_customer_by_id(conn, customer_id, organization_id)
    if not existing:
        return None

    update_data = customer_in.model_dump(exclude_unset=True)
    if not update_data:
        return existing

    fields = []
    values = []
    for key, val in update_data.items():
        fields.append(f"{key} = %s")
        values.append(val)
    
    values.extend((customer_id, organization_id))
    query = f"UPDATE customers SET {', '.join(fields)} WHERE id = %s AND organization_id = %s"
    
    cursor = conn.cursor()
    cursor.execute(query, tuple(values))
    conn.commit()

    return get_customer_by_id(conn, customer_id, organization_id)

def upsert_customer(
    conn: Any,
    organization_id: int,
    name: str,
    phone: str,
    language: Optional[str] = None,
    investigated_course: Optional[str] = None,
    internship_or_course: Optional[str] = None,
    course_duration: Optional[str] = None,
    sheet_url: Optional[str] = None,
    sheet_row: Optional[int] = None,
) -> int:
    """Find-or-create a customer from sheet-driven campaign data by phone number.

    Sheet rows have no real email address, so — matching the working pattern
    already used by /calls/run-sheet — a synthesized, stable email
    (`{digits}@example.com`) is used as the lookup/uniqueness key. Returns
    the customer id.
    """
    clean_phone = re.sub(r"\D", "", phone or "")
    if not clean_phone:
        raise ValueError("Phone number is empty")
    mock_email = f"{clean_phone}@example.com"

    normalized_language = (language or "").strip().lower() or None
    if normalized_language not in (None, "english", "tamil"):
        normalized_language = None

    existing = get_customer_by_email(conn, mock_email, organization_id)
    if existing:
        customer_id = existing["id"]
        update_kwargs = {
            "name": name or existing.get("name"),
            "phone": phone,
            "investigated_course": investigated_course,
            "internship_or_course": internship_or_course,
            "course_duration": course_duration,
        }
        # customers.language is NOT NULL. Only touch it when the sheet/caller
        # actually supplied a valid one, so re-syncing a row with no Language
        # column doesn't wipe out a language already set via the DTMF menu or
        # a previous call.
        if normalized_language is not None:
            update_kwargs["language"] = normalized_language
        update_customer(
            conn, customer_id, organization_id, CustomerUpdate(**update_kwargs)
        )
    else:
        created = create_customer(conn, organization_id, CustomerCreate(
            name=name or "Customer",
            email=mock_email,
            phone=phone,
            # customers.language is NOT NULL; default brand-new customers to
            # english when no language is specified, matching the rest of the
            # app's established default (e.g. app/api/call.py).
            language=normalized_language or "english",
            investigated_course=investigated_course,
            internship_or_course=internship_or_course,
            course_duration=course_duration,
        ))
        customer_id = created["id"]

    if sheet_url is not None or sheet_row is not None:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE customers SET sheet_url=%s, sheet_row=%s "
            "WHERE id=%s AND organization_id=%s",
            (sheet_url, sheet_row, customer_id, organization_id),
        )
        conn.commit()

    return customer_id


def delete_customer(conn: Any, customer_id: int, organization_id: int) -> bool:
    """Deletes a customer by ID. Returns True if successfully deleted, False if customer didn't exist."""
    existing = get_customer_by_id(conn, customer_id, organization_id)
    if not existing:
        return False
        
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM customers WHERE id = %s AND organization_id = %s",
        (customer_id, organization_id),
    )
    conn.commit()
    return True
