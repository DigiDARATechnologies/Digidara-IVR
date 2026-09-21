import unittest
from datetime import datetime
from unittest.mock import MagicMock

from pydantic import ValidationError

from app.schemas.transfer import StaffDestinationCreate
from app.services import transfer_service
from app.services.telephony.plivo_provider import PlivoProvider


def _transfer(**overrides):
    value = {
        "id": 12, "organization_id": 42, "call_log_id": 99,
        "destination_id": 7, "destination_name": "Sales desk",
        "destination_phone": "+919900000000", "status": "requested",
        "provider_call_id": "call-uuid", "provider_bleg_id": None,
        "initiated_by_user_id": 3, "failure_reason": None,
        "requested_at": datetime(2026, 9, 16, 10), "answered_at": None,
        "completed_at": None, "updated_at": datetime(2026, 9, 16, 10),
    }
    value.update(overrides)
    return value


class TransferValidationTests(unittest.TestCase):
    def test_destination_requires_e164(self):
        for phone in ("9876543210", "+12-345", "+123"):
            with self.subTest(phone=phone), self.assertRaises(ValidationError):
                StaffDestinationCreate(name="Sales", phone_e164=phone)

    def test_destination_accepts_e164(self):
        item = StaffDestinationCreate(name="Sales", phone_e164="+919876543210")
        self.assertEqual("+919876543210", item.phone_e164)


class PlivoTransferTests(unittest.TestCase):
    def test_provider_transfers_only_the_a_leg(self):
        client = MagicMock()
        client.calls.update.return_value = {"api_id": "api-1", "message": "call transferred"}
        result = PlivoProvider(
            auth_id="MA" + "1" * 18, auth_token="token", from_number="+14155550100",
            client=client,
        ).transfer_call(call_id="call-uuid", answer_url="https://voice.example.com/transfer")
        client.calls.update.assert_called_once_with(
            call_uuid="call-uuid", legs="aleg",
            aleg_url="https://voice.example.com/transfer", aleg_method="POST",
        )
        self.assertEqual("api-1", result.metadata["api_id"])

    def test_transfer_requests_a_callback_when_one_is_given(self):
        """Plivo's redirect is asynchronous -- a 2xx here only means the
        request was accepted, not that Plivo ever actually fetched
        answer_url. Without a callback there is no way to see a redirect
        that silently never executes."""
        client = MagicMock()
        client.calls.update.return_value = {"api_id": "api-1", "message": "ok"}
        PlivoProvider(
            auth_id="MA" + "1" * 18, auth_token="token", from_number="+14155550100",
            client=client,
        ).transfer_call(
            call_id="call-uuid", answer_url="https://voice.example.com/transfer",
            callback_url="https://voice.example.com/transfer-update-callback",
        )
        client.calls.update.assert_called_once_with(
            call_uuid="call-uuid", legs="aleg",
            aleg_url="https://voice.example.com/transfer", aleg_method="POST",
            callback_url="https://voice.example.com/transfer-update-callback",
            callback_method="POST",
        )


class DestinationDeletionTests(unittest.TestCase):
    def test_delete_removes_the_row_when_it_belongs_to_the_tenant(self):
        db = MagicMock()
        cursor = db.cursor.return_value
        cursor.fetchone.return_value = {"id": 7, "organization_id": 42}
        result = transfer_service.delete_destination(db, 42, 7)
        self.assertTrue(result)
        delete_call = next(c for c in cursor.execute.call_args_list if "DELETE FROM staff_destinations" in c.args[0])
        self.assertEqual((7, 42), delete_call.args[1])
        db.commit.assert_called_once()

    def test_delete_is_a_no_op_for_another_tenants_destination(self):
        db = MagicMock()
        db.cursor.return_value.fetchone.return_value = None
        result = transfer_service.delete_destination(db, 42, 999)
        self.assertFalse(result)
        db.commit.assert_not_called()


class TransferPersistenceTests(unittest.TestCase):
    def test_prepare_is_tenant_scoped_and_idempotent(self):
        db = MagicMock()
        cursor = db.cursor.return_value
        cursor.lastrowid = 12
        cursor.fetchone.side_effect = [
            {"id": 99, "provider_call_id": "call-uuid", "call_sid": "call-uuid",
             "status": "in-progress", "call_status": "in-progress", "correlation_id": "corr-1"},
            {"id": 7, "organization_id": 42, "is_active": True},
            None,
            _transfer(),
        ]
        result = transfer_service.prepare_transfer(
            db, organization_id=42, call_log_id=99, destination_id=7,
            actor_user_id=3, idempotency_key="transfer-unique-1",
        )
        first_sql, first_params = cursor.execute.call_args_list[0].args
        self.assertIn("organization_id=%s", first_sql)
        self.assertEqual((99, 42), first_params)
        insert = next(call for call in cursor.execute.call_args_list if "INSERT INTO call_transfers" in call.args[0])
        self.assertIn("ON DUPLICATE KEY UPDATE", insert.args[0])
        self.assertEqual("transfer-unique-1", insert.args[1][-1])
        self.assertEqual(12, result["id"])
        db.commit.assert_called_once()

    def test_rejects_non_live_call(self):
        db = MagicMock()
        db.cursor.return_value.fetchone.return_value = {
            "id": 99, "provider_call_id": "call-uuid", "status": "completed",
            "call_status": "completed", "correlation_id": "corr-1",
        }
        with self.assertRaisesRegex(ValueError, "live connected"):
            transfer_service.prepare_transfer(
                db, organization_id=42, call_log_id=99, destination_id=7,
                actor_user_id=3, idempotency_key="transfer-unique-1",
            )
        db.commit.assert_not_called()

    def test_reuses_existing_active_transfer(self):
        db = MagicMock()
        db.cursor.return_value.fetchone.side_effect = [
            {"id": 99, "provider_call_id": "call-uuid", "status": "in-progress",
             "call_status": "in-progress", "correlation_id": "corr-1"},
            {"id": 7, "organization_id": 42, "is_active": True},
            {"id": 12},
            _transfer(status="ringing"),
        ]
        result = transfer_service.prepare_transfer(
            db, organization_id=42, call_log_id=99, destination_id=7,
            actor_user_id=3, idempotency_key="another-key",
        )
        self.assertEqual("ringing", result["status"])
        self.assertFalse(any("INSERT INTO call_transfers" in call.args[0] for call in db.cursor.return_value.execute.call_args_list))

    def test_final_no_answer_is_persisted_as_failed(self):
        db = MagicMock()
        db.cursor.return_value.fetchone.side_effect = [_transfer(), _transfer(status="failed", failure_reason="no-answer")]
        result = transfer_service.apply_dial_event(
            db, transfer_id=12, correlation_id="corr-1",
            data={"DialStatus": "no-answer", "DialHangupCause": "no-answer"}, final=True,
        )
        update = db.cursor.return_value.execute.call_args_list[1]
        self.assertIn("organization_id=%s", update.args[0])
        self.assertEqual("failed", update.args[1][0])
        self.assertEqual("failed", result["status"])


class TransferDepartmentTests(unittest.TestCase):
    def test_create_department_persists_and_commits(self):
        db = MagicMock()
        cursor = db.cursor.return_value
        cursor.lastrowid = 5
        cursor.fetchone.return_value = {
            "id": 5, "organization_id": 42, "name": "Sales",
            "description": "Sales desk", "is_active": True,
            "member_count": 0, "created_at": datetime(2026, 9, 19),
            "updated_at": datetime(2026, 9, 19),
        }
        dept = transfer_service.create_department(
            db, 42, {"name": "Sales", "description": "Sales desk"},
        )
        self.assertEqual(5, dept["id"])
        self.assertEqual("Sales", dept["name"])
        db.commit.assert_called_once()
        insert = next(c for c in cursor.execute.call_args_list if "INSERT INTO departments" in c.args[0])
        self.assertIn("organization_id", insert.args[0])
        self.assertEqual((42, "Sales", "Sales desk", True), insert.args[1])

    def test_update_department_syncs_staff_destinations(self):
        db = MagicMock()
        cursor = db.cursor.return_value
        cursor.fetchone.side_effect = [
            {"id": 5, "organization_id": 42, "name": "OldName", "is_active": True},
            {"id": 5, "organization_id": 42, "name": "NewName", "is_active": True, "member_count": 2},
        ]
        result = transfer_service.update_department(
            db, 42, 5, {"name": "NewName"},
        )
        self.assertEqual("NewName", result["name"])
        sync = next(c for c in cursor.execute.call_args_list if "UPDATE staff_destinations SET department=%s" in c.args[0])
        self.assertEqual(("NewName", 42, "OldName"), sync.args[1])
        db.commit.assert_called_once()

    def test_delete_department_unlinks_destinations_and_deletes(self):
        db = MagicMock()
        cursor = db.cursor.return_value
        cursor.fetchone.return_value = {"id": 5, "organization_id": 42, "name": "Education"}
        deleted = transfer_service.delete_department(db, 42, 5)
        self.assertTrue(deleted)
        unlink = next(c for c in cursor.execute.call_args_list if "UPDATE staff_destinations SET department=NULL" in c.args[0])
        self.assertEqual((42, "Education"), unlink.args[1])
        remove = next(c for c in cursor.execute.call_args_list if "DELETE FROM departments" in c.args[0])
        self.assertEqual((5, 42), remove.args[1])
        db.commit.assert_called_once()


class SimultaneousRingingTests(unittest.TestCase):
    def test_get_transfer_phone_numbers_returns_all_department_members(self):
        db = MagicMock()
        cursor = db.cursor.return_value
        cursor.fetchone.return_value = {
            "id": 1, "organization_id": 42, "name": "Alice",
            "phone_e164": "+919876543210", "department": "Sales", "is_active": True,
        }
        cursor.fetchall.return_value = [
            {"phone_e164": "+919876543210"},
            {"phone_e164": "+919876543211"},
            {"phone_e164": "+919876543212"},
        ]
        numbers = transfer_service.get_transfer_phone_numbers(db, 42, 1)
        self.assertEqual(["+919876543210", "+919876543211", "+919876543212"], numbers)
        dept_query = next(c for c in cursor.execute.call_args_list if "WHERE organization_id=%s AND LOWER(TRIM(department))" in c.args[0])
        self.assertEqual((42, "Sales"), dept_query.args[1])

    def test_get_transfer_phone_numbers_single_when_no_department(self):
        db = MagicMock()
        cursor = db.cursor.return_value
        cursor.fetchone.return_value = {
            "id": 2, "organization_id": 42, "name": "Solo Desk",
            "phone_e164": "+919999999999", "department": None, "is_active": True,
        }
        numbers = transfer_service.get_transfer_phone_numbers(db, 42, 2)
        self.assertEqual(["+919999999999"], numbers)

    def test_build_direct_dial_xml_renders_multiple_numbers_simultaneously(self):
        from app.services.plivo_stream import build_direct_dial_xml
        xml = build_direct_dial_xml(
            action_url="https://voice.example.com/action",
            confirm_sound_url="https://voice.example.com/confirm.wav",
            destination_phone=["+919876543210", "+919876543211", "+919876543212"],
        )
        self.assertIn('<Dial action="https://voice.example.com/action"', xml)
        self.assertIn('confirmKey="1"', xml)
        self.assertIn("<Number>+919876543210</Number>", xml)
        self.assertIn("<Number>+919876543211</Number>", xml)
        self.assertIn("<Number>+919876543212</Number>", xml)
        self.assertEqual(3, xml.count("<Number>"))


class TransferDepartmentAPITests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.api.auth import current_admin
        from app.database.db import get_db

        self.db = MagicMock()
        self.cursor = self.db.cursor.return_value
        self.admin = {"id": 1, "organization_id": 42, "role_code": "admin"}

        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[current_admin] = lambda: self.admin
        self.client = TestClient(app)

    def tearDown(self):
        from app.main import app
        app.dependency_overrides.clear()

    def test_get_departments_returns_list(self):
        self.cursor.fetchall.return_value = [
            {
                "id": 1, "organization_id": 42, "name": "Business",
                "description": "Business team", "is_active": True, "member_count": 3,
                "created_at": datetime(2026, 9, 19, 10, 0), "updated_at": datetime(2026, 9, 19, 10, 0),
            }
        ]
        resp = self.client.get("/transfers/departments")
        self.assertEqual(200, resp.status_code)
        data = resp.json()
        self.assertEqual(1, len(data))
        self.assertEqual("Business", data[0]["name"])
        self.assertEqual(3, data[0]["member_count"])

    def test_post_department_creates_new(self):
        self.cursor.lastrowid = 10
        self.cursor.fetchone.return_value = {
            "id": 10, "organization_id": 42, "name": "Support",
            "description": "Customer care", "is_active": True, "member_count": 0,
            "created_at": datetime(2026, 9, 19, 10, 0), "updated_at": datetime(2026, 9, 19, 10, 0),
        }
        resp = self.client.post(
            "/transfers/departments",
            json={"name": "Support", "description": "Customer care"},
        )
        self.assertEqual(201, resp.status_code)
        self.assertEqual("Support", resp.json()["name"])

    def test_delete_department(self):
        self.cursor.fetchone.return_value = {"id": 10, "organization_id": 42, "name": "Support"}
        resp = self.client.delete("/transfers/departments/10")
        self.assertEqual(204, resp.status_code)


class TransferSchemaTests(unittest.TestCase):
    def test_schema_has_transfer_history_and_tenant_constraints(self):
        with open("schema.sql", encoding="utf-8") as handle:
            schema = handle.read()
        self.assertIn("CREATE TABLE IF NOT EXISTS departments", schema)
        self.assertIn("CREATE TABLE IF NOT EXISTS staff_destinations", schema)
        self.assertIn("CREATE TABLE IF NOT EXISTS call_transfers", schema)
        self.assertIn("uq_department_name", schema)
        self.assertIn("uq_call_transfer_idempotency", schema)
        self.assertIn("idx_call_transfer_status", schema)


if __name__ == "__main__":
    unittest.main()

