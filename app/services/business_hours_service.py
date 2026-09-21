"""Per-organization business-hours gate for inbound calls.

An organization with no configured schedule is treated as always open
(fail-open), so this ships without changing behavior for any tenant until
they explicitly set a schedule via ``PUT /business-hours``. Once configured,
calls outside the schedule are declined with a closed message instead of
reaching the AI receptionist.
"""

from datetime import datetime, timezone as dt_timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from app.schemas.business_hours import BusinessHoursSet

DEFAULT_TIMEZONE = "Asia/Kolkata"

_SCHEDULE_COLUMNS = "day_of_week, is_closed, open_time, close_time"


def row_to_dict(row: Any) -> Dict[str, Any]:
    return dict(row) if row else {}


def get_organization_timezone(conn: Any, organization_id: int) -> str:
    cursor = conn.cursor()
    cursor.execute("SELECT timezone FROM organizations WHERE id=%s", (organization_id,))
    row = cursor.fetchone()
    return (row or {}).get("timezone") or DEFAULT_TIMEZONE


def get_schedule(conn: Any, organization_id: int) -> List[Dict[str, Any]]:
    cursor = conn.cursor()
    cursor.execute(
        f"SELECT {_SCHEDULE_COLUMNS} FROM business_hours "
        "WHERE organization_id=%s ORDER BY day_of_week",
        (organization_id,),
    )
    return [row_to_dict(row) for row in cursor.fetchall()]


def set_schedule(
    conn: Any, organization_id: int, schedule_in: BusinessHoursSet,
) -> List[Dict[str, Any]]:
    """Replaces the organization's entire week atomically and stores its timezone."""
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE organizations SET timezone=%s WHERE id=%s",
        (schedule_in.timezone, organization_id),
    )
    cursor.execute("DELETE FROM business_hours WHERE organization_id=%s", (organization_id,))
    for day in schedule_in.days:
        cursor.execute(
            "INSERT INTO business_hours "
            "(organization_id, day_of_week, is_closed, open_time, close_time) "
            "VALUES (%s,%s,%s,%s,%s)",
            (
                organization_id, day.day_of_week, day.is_closed,
                day.open_time, day.close_time,
            ),
        )
    conn.commit()
    return get_schedule(conn, organization_id)


def _resolve_timezone(tz_name: str) -> tuple[str, ZoneInfo]:
    try:
        return tz_name, ZoneInfo(tz_name)
    except Exception:
        return DEFAULT_TIMEZONE, ZoneInfo(DEFAULT_TIMEZONE)


def is_open_now(
    conn: Any, organization_id: int, now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """The check the inbound call flow gates on.

    Returns ``configured=False`` (and ``is_open=True``) for any organization
    that hasn't set a schedule yet, so this feature is opt-in per tenant.
    """
    schedule = get_schedule(conn, organization_id)
    tz_name, tz = _resolve_timezone(get_organization_timezone(conn, organization_id))

    reference = now or datetime.now(dt_timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=dt_timezone.utc)
    local_now = reference.astimezone(tz)
    day_of_week = local_now.weekday()  # Monday=0 .. Sunday=6

    if not schedule:
        return {
            "is_open": True,
            "configured": False,
            "organization_timezone": tz_name,
            "local_time": local_now.isoformat(),
            "day_of_week": day_of_week,
        }

    todays_row = next((row for row in schedule if row["day_of_week"] == day_of_week), None)
    is_open = False
    if todays_row and not todays_row["is_closed"] and todays_row["open_time"] and todays_row["close_time"]:
        current = local_now.strftime("%H:%M")
        is_open = todays_row["open_time"] <= current <= todays_row["close_time"]

    return {
        "is_open": is_open,
        "configured": True,
        "organization_timezone": tz_name,
        "local_time": local_now.isoformat(),
        "day_of_week": day_of_week,
    }
