import unittest
from datetime import date, datetime
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app.api import callbacks as callbacks_api
from app.schemas.callback import CallbackUpdate
from app.services import callback_service


def _task(**overrides):
    value = {
        "id": 8,
        "organization_id": 42,
        "customer_id": 5,
        "campaign_id": 7,
        "source_call_log_id": 99,
        "reminder_type": "callback",
        "source": "realtime",
        "requested_date": None,
        "scheduled_at": None,
        "timezone": "Asia/Kolkata",
        "status": "pending",
        "assigned_user_id": None,
        "assigned_user_name": None,
        "notes": None,
        "completed_at": None,
        "completed_by_user_id": None,
        "customer_name": "Anita",
        "customer_phone": "+919900000000",
        "call_summary": "Requested a callback.",
        "lead_score": 65,
        "qualification": "warm",
        "created_at": datetime(2026, 9, 16, 10, 0),
        "updated_at": datetime(2026, 9, 16, 10, 0),
    }
    value.update(overrides)
    return value


class CallbackDateTests(unittest.TestCase):
    def test_normalizes_iso_date_without_fabricating_missing_values(self):
        self.assertEqual(date(2026, 9, 20), callback_service.normalize_requested_date("2026-09-20"))
        self.assertIsNone(callback_service.normalize_requested_date("N/A"))
        self.assertIsNone(callback_service.normalize_requested_date("next week"))


class CallbackPersistenceTests(unittest.TestCase):
    def test_ensure_for_call_is_tenant_scoped_and_idempotent(self):
        db = MagicMock()
        cursor = db.cursor.return_value
        cursor.fetchone.side_effect = [
            {"id": 99, "customer_id": 5, "campaign_id": 7, "timezone": "Asia/Kolkata"},
            _task(requested_date=date(2026, 9, 20)),
        ]
        with patch("app.services.crm_outbox_service.emit_callback_required") as emit:
            result = callback_service.ensure_for_call(
                db, organization_id=42, call_log_id=99,
                requested_date="2026-09-20", source="post_call_analysis",
            )
        first_sql, first_params = cursor.execute.call_args_list[0].args
        self.assertIn("cl.organization_id=%s", first_sql)
        self.assertEqual((99, 42), first_params)
        insert_sql, insert_params = cursor.execute.call_args_list[1].args
        self.assertIn("ON DUPLICATE KEY UPDATE", insert_sql)
        self.assertEqual("callback:call:99", insert_params[-1])
        self.assertEqual(date(2026, 9, 20), result["requested_date"])
        emit.assert_called_once_with(db, unittest.mock.ANY, commit=False)
        db.commit.assert_called_once()

    def test_rejects_call_from_another_organization(self):
        db = MagicMock()
        db.cursor.return_value.fetchone.return_value = None
        with self.assertRaises(ValueError):
            callback_service.ensure_for_call(db, organization_id=42, call_log_id=99)
        db.commit.assert_not_called()

    def test_list_filters_are_always_tenant_scoped(self):
        db = MagicMock()
        db.cursor.return_value.fetchall.return_value = []
        callback_service.list_callbacks(db, 42, status="pending", search="Anita")
        sql, params = db.cursor.return_value.execute.call_args.args
        self.assertIn("fr.organization_id=%s", sql)
        self.assertEqual(42, params[0])
        self.assertIn("pending", params)


class CallbackUpdateTests(unittest.TestCase):
    def test_cannot_assign_user_from_another_organization(self):
        db = MagicMock()
        db.cursor.return_value.fetchone.side_effect = [_task(), None]
        with self.assertRaises(ValueError):
            callback_service.update_callback(
                db, organization_id=42, callback_id=8, actor_user_id=3,
                changes={"assigned_user_id": 999},
            )
        db.commit.assert_not_called()

    def test_completing_task_clears_call_flag_and_writes_audit(self):
        db = MagicMock()
        db.cursor.return_value.fetchone.side_effect = [_task(), _task(status="completed")]
        result = callback_service.update_callback(
            db, organization_id=42, callback_id=8, actor_user_id=3,
            changes={"status": "completed"},
        )
        calls = db.cursor.return_value.execute.call_args_list
        self.assertTrue(any("followup_required=FALSE" in call.args[0] for call in calls))
        self.assertTrue(any("INSERT INTO audit_logs" in call.args[0] for call in calls))
        self.assertEqual("completed", result["status"])
        db.commit.assert_called_once()


class CallbackApiTests(unittest.TestCase):
    def test_list_uses_authenticated_organization(self):
        with patch.object(callback_service, "list_callbacks", return_value=[]) as list_callbacks:
            callbacks_api.read_callbacks(admin={"organization_id": 42, "id": 3}, db=MagicMock())
        self.assertEqual(42, list_callbacks.call_args.args[1])

    def test_update_uses_actor_and_tenant(self):
        with patch.object(callback_service, "update_callback", return_value=_task()) as update_callback:
            callbacks_api.update_callback(
                8, CallbackUpdate(status="assigned", assigned_user_id=3),
                admin={"organization_id": 42, "id": 3}, db=MagicMock(),
            )
        kwargs = update_callback.call_args.kwargs
        self.assertEqual(42, kwargs["organization_id"])
        self.assertEqual(3, kwargs["actor_user_id"])

    def test_unknown_task_returns_404(self):
        with patch.object(callback_service, "update_callback", return_value=None):
            with self.assertRaises(HTTPException) as raised:
                callbacks_api.update_callback(
                    8, CallbackUpdate(status="completed"),
                    admin={"organization_id": 42, "id": 3}, db=MagicMock(),
                )
        self.assertEqual(404, raised.exception.status_code)


class CallbackSchemaTests(unittest.TestCase):
    def test_schema_has_tenant_idempotency_and_assignment(self):
        with open("schema.sql", encoding="utf-8") as handle:
            schema = handle.read()
        self.assertIn("UNIQUE KEY uq_followup_idempotency", schema)
        self.assertIn("idx_reminder_tenant_status_due", schema)
        self.assertIn("completed_by_user_id INT NULL", schema)


if __name__ == "__main__":
    unittest.main()
