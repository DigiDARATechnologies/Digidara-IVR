"""Explicit demo-only use case for the Nectar Building A HVAC scenario."""

from typing import Any

from app.facility.infrastructure.repository import FacilityRepository


DEMO_SITE = ("Building A", "BLDG-A", "Asia/Kolkata")
DEMO_ASSETS = (
    ("Chiller-01", "Chiller-01", "chiller", "operational", "Central plant", {"normal_power_kw": 100.0}),
    ("AHU-02", "AHU-02", "air_handling_unit", "degraded", "Third floor", {"design_airflow_cfm": 12000}),
)
DEMO_READINGS = (
    (None, "BLDG-A-TEMP", "temperature", 29.4, "C"),
    ("Chiller-01", "CHILLER-01-POWER", "power_kw", 118.0, "kW"),
    ("AHU-02", "AHU-02-AIRFLOW", "airflow_cfm", 7200.0, "cfm"),
)


def seed_demo_facility(repository: FacilityRepository, organization_id: int) -> dict[str, Any]:
    site = repository.get_site_by_code(organization_id, DEMO_SITE[1])
    if not site:
        site = repository.create_site(organization_id, *DEMO_SITE)
    site_id = site["id"]

    asset_ids: dict[str, int] = {}
    assets_created = 0
    for asset in DEMO_ASSETS:
        existing = repository.get_asset_by_code(site_id, asset[0])
        if existing:
            asset_ids[asset[0]] = existing["id"]
            continue
        asset_ids[asset[0]] = repository.create_asset(site_id, asset)
        assets_created += 1

    sensors_created = 0
    for asset_code, sensor_code, metric, value, unit in DEMO_READINGS:
        if repository.has_sensor(site_id, sensor_code):
            continue
        repository.create_sensor_reading(site_id, asset_ids[asset_code] if asset_code else None, (sensor_code, metric, value, unit))
        sensors_created += 1

    alert_created = 0
    if not repository.has_active_alert(site_id, "AHU-02 low airflow"):
        repository.create_alert(site_id, asset_ids["AHU-02"], "high", "AHU-02 low airflow", "Measured airflow is 40% below design airflow.")
        alert_created = 1
    if not repository.has_relationship(asset_ids["Chiller-01"], asset_ids["AHU-02"], "supplies"):
        repository.create_relationship(asset_ids["Chiller-01"], asset_ids["AHU-02"], "supplies")
    repository.commit()
    return {
        "site": site,
        "assets_created": assets_created,
        "sensors_created": sensors_created,
        "alerts_created": alert_created,
        "message": "Building A HVAC demo scenario is ready.",
    }
