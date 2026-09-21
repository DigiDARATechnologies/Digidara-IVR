import unittest
from unittest.mock import MagicMock

from pydantic import ValidationError

from app.schemas.ivr import IvrSettingsUpdate
from app.services import ivr_service


class IvrSchemaTests(unittest.TestCase):
    def test_active_menu_requires_an_active_option_and_unique_digits(self):
        with self.assertRaises(ValidationError):
            IvrSettingsUpdate(is_active=True)
        with self.assertRaises(ValidationError):
            IvrSettingsUpdate(options=[
                {"digit": "1", "label": "Sales", "campaign_id": 1},
                {"digit": "1", "label": "Support", "campaign_id": 2},
            ])


class IvrRoutingTests(unittest.TestCase):
    def test_disabled_menu_is_not_exposed_to_callers(self):
        db = MagicMock()
        db.cursor.return_value.fetchone.return_value = {"id": 4, "is_active": False}
        self.assertIsNone(ivr_service.get_live_menu(db, 42, "english"))

    def test_route_selection_is_tenant_scoped_and_updates_call_campaign(self):
        db = MagicMock()
        cursor = db.cursor.return_value
        cursor.fetchone.side_effect = [
            None,
            {"id": 8, "digit": "1", "label": "Sales", "campaign_id": 20},
        ]
        result = ivr_service.route_selection(
            db, organization_id=42, call_log_id=99, digit="1",
        )
        option_query = cursor.execute.call_args_list[1]
        self.assertIn("s.organization_id=%s", option_query.args[0])
        self.assertEqual((42, "1"), option_query.args[1])
        update = cursor.execute.call_args_list[3]
        self.assertIn("organization_id=%s", update.args[0])
        self.assertEqual((20, 99, 42), update.args[1])
        self.assertEqual("ai", result["route_type"])
        self.assertEqual(20, result["campaign_id"])
        db.commit.assert_called_once()

    def test_callback_retry_keeps_original_route(self):
        db = MagicMock()
        db.cursor.return_value.fetchone.return_value = {"campaign_id": 20, "destination_id": None}
        result = ivr_service.route_selection(db, organization_id=42, call_log_id=99, digit="9")
        self.assertEqual(
            {"route_type": "ai", "campaign_id": 20, "label": None, "replayed": True}, result,
        )
        self.assertEqual(1, db.cursor.return_value.execute.call_count)
        db.commit.assert_not_called()

    def test_option_routed_to_a_human_destination_skips_the_ai_entirely(self):
        db = MagicMock()
        cursor = db.cursor.return_value
        cursor.fetchone.side_effect = [
            None,  # no previous selection
            {"id": 9, "digit": "2", "label": "Support", "campaign_id": None, "destination_id": 7},
            {"name": "Support Desk", "phone_e164": "+919876500000"},  # destination lookup
        ]
        result = ivr_service.route_selection(
            db, organization_id=42, call_log_id=99, digit="2",
        )
        self.assertEqual("human", result["route_type"])
        self.assertEqual(7, result["destination_id"])
        self.assertEqual("+919876500000", result["destination_phone"])
        # A human-routed selection must not overwrite call_logs.campaign_id
        # with NULL, and no AI campaign update should run at all.
        update_calls = [c for c in cursor.execute.call_args_list if "UPDATE call_logs" in c.args[0]]
        self.assertEqual([], update_calls)
        db.commit.assert_called_once()

    def test_spoken_department_name_routes_without_any_digit(self):
        db = MagicMock()
        cursor = db.cursor.return_value
        cursor.fetchone.side_effect = [None]  # no previous selection
        cursor.fetchall.return_value = [
            {"id": 5, "digit": "1", "label": "Business", "campaign_id": 11},
            {"id": 6, "digit": "2", "label": "Support", "campaign_id": 12},
            {"id": 7, "digit": "3", "label": "Education", "campaign_id": 13},
        ]
        result = ivr_service.route_selection(
            db, organization_id=42, call_log_id=99, speech_text="uh yeah support please",
        )
        self.assertEqual(12, result["campaign_id"])
        insert = cursor.execute.call_args_list[-2]
        self.assertIn("INSERT INTO call_ivr_selections", insert.args[0])
        self.assertEqual((42, 99, 6, "2", "Support", 12, None), insert.args[1])

    def test_digit_is_tried_before_falling_back_to_speech(self):
        db = MagicMock()
        cursor = db.cursor.return_value
        cursor.fetchone.side_effect = [
            None,
            {"id": 5, "digit": "1", "label": "Business", "campaign_id": 11},
        ]
        result = ivr_service.route_selection(
            db, organization_id=42, call_log_id=99, digit="1", speech_text="support",
        )
        self.assertEqual(11, result["campaign_id"])
        cursor.fetchall.assert_not_called()

    def test_unrecognized_speech_returns_none(self):
        db = MagicMock()
        cursor = db.cursor.return_value
        cursor.fetchone.side_effect = [None]
        cursor.fetchall.return_value = [
            {"id": 5, "digit": "1", "label": "Business", "campaign_id": 11},
        ]
        result = ivr_service.route_selection(
            db, organization_id=42, call_log_id=99, speech_text="I want to talk about pricing",
        )
        self.assertIsNone(result)
        db.commit.assert_not_called()

    def test_update_rejects_campaign_from_another_tenant(self):
        db = MagicMock()
        db.cursor.return_value.fetchall.return_value = [{"id": 1}]
        with self.assertRaisesRegex(ValueError, "organization"):
            ivr_service.update_settings(
                db, 42,
                {"is_active": True, "timeout_seconds": 7, "prompt_english": "", "prompt_tamil": "",
                 "options": [{"digit": "1", "label": "Sales", "campaign_id": 1, "is_active": True, "sort_order": 1}, {"digit": "2", "label": "Support", "campaign_id": 2, "is_active": True, "sort_order": 2}]},
                actor_user_id=3,
            )
        db.commit.assert_not_called()


class IvrSchemaPresenceTests(unittest.TestCase):
    def test_schema_has_tenant_scoped_configuration_and_idempotent_selection(self):
        with open("schema.sql", encoding="utf-8") as handle:
            schema = handle.read()
        self.assertIn("CREATE TABLE IF NOT EXISTS organization_ivr_settings", schema)
        self.assertIn("CREATE TABLE IF NOT EXISTS organization_ivr_options", schema)
        self.assertIn("CREATE TABLE IF NOT EXISTS call_ivr_selections", schema)
        self.assertIn("uq_call_ivr_selection", schema)


if __name__ == "__main__":
    unittest.main()
