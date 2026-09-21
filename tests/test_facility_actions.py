"""Safety regression tests for confirmation-gated Facility write actions."""

import json
import unittest
from datetime import datetime, timedelta, timezone

from app.facility.application.service_request_actions import FacilityActionError, FacilityActionService
from app.facility.domain.contracts import ServiceRequestDraftInput


class _ActionRepository:
    def __init__(self):
        self.confirmations = {}
        self.created_requests = []
        self.statuses = []
        self.audits = []
        self.commits = 0

    def get_site_by_code(self, organization_id, site_code):
        return {"id": 1, "code": "BLDG-A"} if organization_id == 42 and site_code == "BLDG-A" else None

    def get_asset_by_code(self, site_id, asset_code):
        return {"id": 2} if site_id == 1 and asset_code == "AHU-02" else None

    def create_action_confirmation(self, confirmation_id, organization_id, actor_user_id, action_type, payload, expires_at):
        self.confirmations[confirmation_id] = {
            "id": confirmation_id, "organization_id": organization_id, "requested_by_user_id": actor_user_id,
            "action_type": action_type, "payload_json": json.dumps(payload), "status": "pending", "expires_at": expires_at,
        }

    def get_action_confirmation_for_update(self, confirmation_id, organization_id, actor_user_id):
        confirmation = self.confirmations.get(confirmation_id)
        if not confirmation or confirmation["organization_id"] != organization_id or confirmation["requested_by_user_id"] != actor_user_id:
            return None
        return confirmation

    def set_action_confirmation_status(self, confirmation_id, status):
        self.confirmations[confirmation_id]["status"] = status
        self.statuses.append(status)

    def create_service_request(self, request_number, payload, actor_user_id):
        request = {"id": len(self.created_requests) + 1, "request_number": request_number, **payload, "status": "open", "created_at": datetime.now(timezone.utc)}
        self.created_requests.append(request)
        return request

    def record_action_audit(self, *args):
        self.audits.append(args)

    def commit(self):
        self.commits += 1

    def rollback(self):
        raise AssertionError("The happy path must not roll back")


class FacilityActionTests(unittest.TestCase):
    def setUp(self):
        self.repository = _ActionRepository()
        self.service = FacilityActionService(self.repository, 42, 9)
        self.draft = ServiceRequestDraftInput(
            site_code="BLDG-A", asset_code="AHU-02", title="Inspect low airflow",
            description="Inspect AHU-02 because its measured airflow is below design.", priority="high",
        )

    def test_prepare_never_creates_a_service_request(self):
        confirmation = self.service.prepare_service_request(self.draft)
        self.assertEqual("pending", confirmation["status"])
        self.assertEqual([], self.repository.created_requests)
        self.assertIn(confirmation["id"], self.repository.confirmations)

    def test_explicit_confirmation_creates_once_and_writes_audit_record(self):
        confirmation = self.service.prepare_service_request(self.draft)
        request = self.service.confirm_and_create_service_request(confirmation["id"])

        self.assertEqual("open", request["status"])
        self.assertEqual("consumed", self.repository.confirmations[confirmation["id"]]["status"])
        self.assertEqual(1, len(self.repository.created_requests))
        self.assertEqual(1, len(self.repository.audits))
        with self.assertRaises(FacilityActionError):
            self.service.confirm_and_create_service_request(confirmation["id"])
        self.assertEqual(1, len(self.repository.created_requests))

    def test_expired_confirmation_cannot_create_a_service_request(self):
        confirmation = self.service.prepare_service_request(self.draft)
        self.repository.confirmations[confirmation["id"]]["expires_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)

        with self.assertRaises(FacilityActionError):
            self.service.confirm_and_create_service_request(confirmation["id"])
        self.assertEqual("expired", self.repository.confirmations[confirmation["id"]]["status"])
        self.assertEqual([], self.repository.created_requests)


if __name__ == "__main__":
    unittest.main()
