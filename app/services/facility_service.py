"""Compatibility facade for Facility Operations use cases.

New facility behavior belongs in ``app.facility``. This facade preserves the
existing service import path while the codebase transitions safely.
"""

from typing import Any

from app.facility.application.demo_scenario import seed_demo_facility as _seed_demo_facility
from app.facility.application.facility_queries import get_facility_overview as _get_facility_overview
from app.facility.infrastructure.repository import FacilityRepository, _row_with_metadata


def _row(row: Any) -> dict[str, Any]:
    """Compatibility alias retained for existing callers and focused tests."""
    return _row_with_metadata(row)


def get_facility_overview(conn: Any, organization_id: int) -> dict[str, list[dict[str, Any]]]:
    return _get_facility_overview(FacilityRepository(conn), organization_id)


def seed_demo_facility(conn: Any, organization_id: int) -> dict[str, Any]:
    return _seed_demo_facility(FacilityRepository(conn), organization_id)
