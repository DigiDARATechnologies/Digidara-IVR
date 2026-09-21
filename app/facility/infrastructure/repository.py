"""Raw-SQL repository for the tenant-scoped facility data model."""

import json
from typing import Any


def _row_with_metadata(row: Any) -> dict[str, Any]:
    result = dict(row)
    metadata = result.pop("metadata_json", None)
    if isinstance(metadata, str):
        try:
            result["metadata"] = json.loads(metadata)
        except json.JSONDecodeError:
            result["metadata"] = {}
    else:
        result["metadata"] = metadata or {}
    return result


class FacilityRepository:
    """Keeps SQL and tenant joins out of the application/use-case layer."""

    def __init__(self, conn: Any):
        self._conn = conn

    def list_sites(self, organization_id: int) -> list[dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT id,name,code,timezone FROM facility_sites WHERE organization_id=%s ORDER BY name",
            (organization_id,),
        )
        return [dict(item) for item in cursor.fetchall()]

    def list_assets(self, organization_id: int) -> list[dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute(
            """SELECT a.id,a.site_id,a.asset_code,a.name,a.asset_type,a.status,a.location,a.metadata_json
               FROM facility_assets a JOIN facility_sites s ON s.id=a.site_id
               WHERE s.organization_id=%s ORDER BY a.asset_code""",
            (organization_id,),
        )
        return [_row_with_metadata(item) for item in cursor.fetchall()]

    def list_active_alerts(self, organization_id: int) -> list[dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute(
            """SELECT al.id,al.site_id,al.asset_id,al.severity,al.title,al.message,al.status,al.opened_at
               FROM facility_alerts al JOIN facility_sites s ON s.id=al.site_id
               WHERE s.organization_id=%s AND al.status IN ('active','acknowledged')
               ORDER BY FIELD(al.severity,'critical','high','medium','low'),al.opened_at DESC""",
            (organization_id,),
        )
        return [dict(item) for item in cursor.fetchall()]

    def list_latest_readings(self, organization_id: int) -> list[dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute(
            """SELECT r.id,r.asset_id,r.sensor_code,r.metric,r.value,r.unit,r.observed_at
               FROM facility_sensor_readings r LEFT JOIN facility_assets a ON a.id=r.asset_id
               LEFT JOIN facility_sites s ON s.id=COALESCE(a.site_id,r.site_id)
               WHERE s.organization_id=%s ORDER BY r.observed_at DESC LIMIT 50""",
            (organization_id,),
        )
        return [dict(item) for item in cursor.fetchall()]

    def list_open_service_requests(self, organization_id: int) -> list[dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute(
            """SELECT sr.id,sr.site_id,sr.asset_id,sr.request_number,sr.title,sr.description,
                      sr.priority,sr.status,sr.created_at
               FROM facility_service_requests sr JOIN facility_sites s ON s.id=sr.site_id
               WHERE s.organization_id=%s AND sr.status IN ('open','in_progress')
               ORDER BY sr.created_at DESC""",
            (organization_id,),
        )
        return [dict(item) for item in cursor.fetchall()]

    def get_asset_details(self, organization_id: int, asset_reference: str) -> dict[str, Any] | None:
        cursor = self._conn.cursor()
        cursor.execute(
            """SELECT a.id,a.site_id,a.asset_code,a.name,a.asset_type,a.status,a.location,a.metadata_json,
                      s.name AS site_name,s.code AS site_code
               FROM facility_assets a JOIN facility_sites s ON s.id=a.site_id
               WHERE s.organization_id=%s AND (a.asset_code=%s OR a.name=%s)""",
            (organization_id, asset_reference, asset_reference),
        )
        row = cursor.fetchone()
        return _row_with_metadata(row) if row else None

    def list_sensor_data(self, organization_id: int, asset_reference: str, metric: str | None = None) -> list[dict[str, Any]]:
        cursor = self._conn.cursor()
        if metric:
            cursor.execute(
                """SELECT r.id,r.asset_id,r.sensor_code,r.metric,r.value,r.unit,r.observed_at
                   FROM facility_sensor_readings r JOIN facility_assets a ON a.id=r.asset_id
                   JOIN facility_sites s ON s.id=a.site_id
                   WHERE s.organization_id=%s AND (a.asset_code=%s OR a.name=%s) AND r.metric=%s
                   ORDER BY r.observed_at DESC LIMIT 25""",
                (organization_id, asset_reference, asset_reference, metric),
            )
        else:
            cursor.execute(
                """SELECT r.id,r.asset_id,r.sensor_code,r.metric,r.value,r.unit,r.observed_at
                   FROM facility_sensor_readings r JOIN facility_assets a ON a.id=r.asset_id
                   JOIN facility_sites s ON s.id=a.site_id
                   WHERE s.organization_id=%s AND (a.asset_code=%s OR a.name=%s)
                   ORDER BY r.observed_at DESC LIMIT 25""",
                (organization_id, asset_reference, asset_reference),
            )
        return [dict(item) for item in cursor.fetchall()]

    def list_asset_relationships(self, organization_id: int, asset_reference: str) -> list[dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute(
            """SELECT r.relationship_type,from_asset.asset_code AS from_asset_code,
                      to_asset.asset_code AS to_asset_code,to_asset.name AS related_asset_name,to_asset.status AS related_asset_status
               FROM facility_asset_relationships r
               JOIN facility_assets from_asset ON from_asset.id=r.from_asset_id
               JOIN facility_assets to_asset ON to_asset.id=r.to_asset_id
               JOIN facility_sites s ON s.id=from_asset.site_id
               WHERE s.organization_id=%s
                 AND (from_asset.asset_code=%s OR from_asset.name=%s OR to_asset.asset_code=%s OR to_asset.name=%s)
               ORDER BY r.relationship_type,to_asset.asset_code""",
            (organization_id, asset_reference, asset_reference, asset_reference, asset_reference),
        )
        return [dict(item) for item in cursor.fetchall()]

    def get_site_by_code(self, organization_id: int, code: str) -> dict[str, Any] | None:
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT id,name,code,timezone FROM facility_sites WHERE organization_id=%s AND code=%s",
            (organization_id, code),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def create_site(self, organization_id: int, name: str, code: str, timezone: str) -> dict[str, Any]:
        cursor = self._conn.cursor()
        cursor.execute(
            "INSERT INTO facility_sites (organization_id,name,code,timezone) VALUES (%s,%s,%s,%s)",
            (organization_id, name, code, timezone),
        )
        return {"id": cursor.lastrowid, "name": name, "code": code, "timezone": timezone}

    def get_asset_by_code(self, site_id: int, asset_code: str) -> dict[str, Any] | None:
        cursor = self._conn.cursor()
        cursor.execute("SELECT id FROM facility_assets WHERE site_id=%s AND asset_code=%s", (site_id, asset_code))
        row = cursor.fetchone()
        return dict(row) if row else None

    def create_asset(self, site_id: int, asset: tuple[str, str, str, str, str, dict[str, Any]]) -> int:
        code, name, asset_type, status, location, metadata = asset
        cursor = self._conn.cursor()
        cursor.execute(
            """INSERT INTO facility_assets (site_id,asset_code,name,asset_type,status,location,metadata_json)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (site_id, code, name, asset_type, status, location, json.dumps(metadata)),
        )
        return cursor.lastrowid

    def has_sensor(self, site_id: int, sensor_code: str) -> bool:
        cursor = self._conn.cursor()
        cursor.execute("SELECT id FROM facility_sensor_readings WHERE site_id=%s AND sensor_code=%s", (site_id, sensor_code))
        return bool(cursor.fetchone())

    def create_sensor_reading(self, site_id: int, asset_id: int | None, reading: tuple[str, str, float, str]) -> None:
        sensor_code, metric, value, unit = reading
        cursor = self._conn.cursor()
        cursor.execute(
            """INSERT INTO facility_sensor_readings (site_id,asset_id,sensor_code,metric,value,unit)
               VALUES (%s,%s,%s,%s,%s,%s)""",
            (site_id, asset_id, sensor_code, metric, value, unit),
        )

    def has_active_alert(self, site_id: int, title: str) -> bool:
        cursor = self._conn.cursor()
        cursor.execute("SELECT id FROM facility_alerts WHERE site_id=%s AND title=%s AND status='active'", (site_id, title))
        return bool(cursor.fetchone())

    def create_alert(self, site_id: int, asset_id: int, severity: str, title: str, message: str) -> None:
        cursor = self._conn.cursor()
        cursor.execute(
            """INSERT INTO facility_alerts (site_id,asset_id,severity,title,message,status)
               VALUES (%s,%s,%s,%s,%s,'active')""",
            (site_id, asset_id, severity, title, message),
        )

    def has_relationship(self, from_asset_id: int, to_asset_id: int, relationship_type: str) -> bool:
        cursor = self._conn.cursor()
        cursor.execute(
            """SELECT id FROM facility_asset_relationships
               WHERE from_asset_id=%s AND to_asset_id=%s AND relationship_type=%s""",
            (from_asset_id, to_asset_id, relationship_type),
        )
        return bool(cursor.fetchone())

    def create_relationship(self, from_asset_id: int, to_asset_id: int, relationship_type: str) -> None:
        cursor = self._conn.cursor()
        cursor.execute(
            """INSERT INTO facility_asset_relationships (from_asset_id,to_asset_id,relationship_type)
               VALUES (%s,%s,%s)""",
            (from_asset_id, to_asset_id, relationship_type),
        )

    def create_action_confirmation(
        self, confirmation_id: str, organization_id: int, actor_user_id: int,
        action_type: str, payload: dict[str, Any], expires_at: Any,
    ) -> None:
        cursor = self._conn.cursor()
        cursor.execute(
            """INSERT INTO facility_action_confirmations
               (id,organization_id,requested_by_user_id,action_type,payload_json,status,expires_at)
               VALUES (%s,%s,%s,%s,%s,'pending',%s)""",
            (confirmation_id, organization_id, actor_user_id, action_type, json.dumps(payload), expires_at),
        )

    def get_action_confirmation_for_update(
        self, confirmation_id: str, organization_id: int, actor_user_id: int,
    ) -> dict[str, Any] | None:
        cursor = self._conn.cursor()
        cursor.execute(
            """SELECT id,action_type,payload_json,status,expires_at
               FROM facility_action_confirmations
               WHERE id=%s AND organization_id=%s AND requested_by_user_id=%s FOR UPDATE""",
            (confirmation_id, organization_id, actor_user_id),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def set_action_confirmation_status(self, confirmation_id: str, status: str) -> None:
        cursor = self._conn.cursor()
        cursor.execute(
            "UPDATE facility_action_confirmations SET status=%s,consumed_at=CASE WHEN %s='consumed' THEN NOW() ELSE consumed_at END WHERE id=%s",
            (status, status, confirmation_id),
        )

    def create_service_request(self, request_number: str, payload: dict[str, Any], actor_user_id: int) -> dict[str, Any]:
        cursor = self._conn.cursor()
        cursor.execute(
            """INSERT INTO facility_service_requests
               (site_id,asset_id,request_number,title,description,priority,status,requested_by_user_id)
               VALUES (%s,%s,%s,%s,%s,%s,'open',%s)""",
            (
                payload["site_id"], payload["asset_id"], request_number, payload["title"],
                payload["description"], payload["priority"], actor_user_id,
            ),
        )
        request_id = cursor.lastrowid
        cursor.execute(
            """SELECT id,site_id,asset_id,request_number,title,description,priority,status,created_at
               FROM facility_service_requests WHERE id=%s""",
            (request_id,),
        )
        return dict(cursor.fetchone())

    def record_action_audit(
        self, organization_id: int, actor_user_id: int, action: str, resource_type: str,
        resource_id: str, metadata: dict[str, Any],
    ) -> None:
        cursor = self._conn.cursor()
        cursor.execute(
            """INSERT INTO audit_logs (organization_id,actor_user_id,action,resource_type,resource_id,result,metadata_json)
               VALUES (%s,%s,%s,%s,%s,'success',%s)""",
            (organization_id, actor_user_id, action, resource_type, resource_id, json.dumps(metadata)),
        )

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()
