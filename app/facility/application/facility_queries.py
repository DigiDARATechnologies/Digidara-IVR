"""Read use cases for the Facility Operations product."""

from typing import Any

from app.facility.infrastructure.repository import FacilityRepository


def get_facility_overview(repository: FacilityRepository, organization_id: int) -> dict[str, list[dict[str, Any]]]:
    return {
        "sites": repository.list_sites(organization_id),
        "assets": repository.list_assets(organization_id),
        "active_alerts": repository.list_active_alerts(organization_id),
        "latest_readings": repository.list_latest_readings(organization_id),
        "open_service_requests": repository.list_open_service_requests(organization_id),
    }
