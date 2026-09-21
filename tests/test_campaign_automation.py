"""Tests for the bulk-campaign auto-progression fix.

Covers the three pieces that were previously missing/broken:
  - customer_service.upsert_customer (did not exist)
  - google_sheets_service.update_sheet_status (did not exist)
  - telephony_service.is_suppressed (the new do-not-call gate)
"""

import unittest
from unittest.mock import MagicMock, patch

from app.services import customer_service, telephony_service
from app.services.google_sheets_service import update_sheet_status


class UpsertCustomerTests(unittest.TestCase):
    def test_creates_new_customer_when_none_matches_phone(self):
        conn = MagicMock()
        with patch.object(customer_service, "get_customer_by_email", return_value=None) as get_mock, \
             patch.object(customer_service, "create_customer", return_value={"id": 42}) as create_mock, \
             patch.object(customer_service, "update_customer") as update_mock:
            customer_id = customer_service.upsert_customer(
                conn, organization_id=9, name="Asha", phone="9994146080", language="tamil",
                investigated_course="AI Systems Engineer",
                sheet_url="https://sheet.example", sheet_row=5,
            )

        self.assertEqual(customer_id, 42)
        get_mock.assert_called_once_with(conn, "9994146080@example.com", 9)
        create_mock.assert_called_once()
        update_mock.assert_not_called()
        self.assertEqual(9, create_mock.call_args[0][1])
        created_payload = create_mock.call_args[0][2]
        self.assertEqual(created_payload.email, "9994146080@example.com")
        self.assertEqual(created_payload.phone, "9994146080")
        self.assertEqual(created_payload.language, "tamil")

    def test_updates_existing_customer_matched_by_synthesized_email(self):
        conn = MagicMock()
        with patch.object(customer_service, "get_customer_by_email", return_value={"id": 7, "name": "Old"}), \
             patch.object(customer_service, "create_customer") as create_mock, \
             patch.object(customer_service, "update_customer") as update_mock:
            customer_id = customer_service.upsert_customer(
                conn, organization_id=9, name="New Name", phone="+91 99941 46080",
            )

        self.assertEqual(customer_id, 7)
        create_mock.assert_not_called()
        update_mock.assert_called_once()
        self.assertEqual(update_mock.call_args[0][1], 7)

    def test_rejects_empty_phone(self):
        conn = MagicMock()
        with self.assertRaises(ValueError):
            customer_service.upsert_customer(conn, organization_id=9, name="No Phone", phone="")

    def test_invalid_or_missing_language_defaults_to_english_on_create(self):
        # customers.language is NOT NULL, so a brand-new customer can never be
        # created with language=None -- it must default to a real value.
        conn = MagicMock()
        with patch.object(customer_service, "get_customer_by_email", return_value=None), \
             patch.object(customer_service, "create_customer", return_value={"id": 1}) as create_mock, \
             patch.object(customer_service, "update_customer"):
            customer_service.upsert_customer(conn, organization_id=9, name="X", phone="9000000000", language="french")

        created_payload = create_mock.call_args[0][2]
        self.assertEqual(created_payload.language, "english")

    def test_no_language_column_still_creates_customer_with_default_language(self):
        # Regression test: a sheet row with no Language column (language=None)
        # must not raise an IntegrityError against the NOT NULL column.
        conn = MagicMock()
        with patch.object(customer_service, "get_customer_by_email", return_value=None), \
             patch.object(customer_service, "create_customer", return_value={"id": 2}) as create_mock, \
             patch.object(customer_service, "update_customer"):
            customer_service.upsert_customer(conn, organization_id=9, name="Y", phone="9000000001", language=None)

        created_payload = create_mock.call_args[0][2]
        self.assertEqual(created_payload.language, "english")

    def test_updating_existing_customer_without_language_preserves_existing_value(self):
        # A re-synced sheet row with no Language column must not wipe out a
        # language already set (e.g. via the DTMF menu or a previous call).
        conn = MagicMock()
        with patch.object(customer_service, "get_customer_by_email", return_value={"id": 7, "name": "Old"}), \
             patch.object(customer_service, "create_customer") as create_mock, \
             patch.object(customer_service, "update_customer") as update_mock:
            customer_service.upsert_customer(conn, organization_id=9, name="Old", phone="9000000002", language=None)

        create_mock.assert_not_called()
        updated_payload = update_mock.call_args[0][3]
        self.assertNotIn("language", updated_payload.model_fields_set)


class UpdateSheetStatusTests(unittest.TestCase):
    def test_delegates_to_update_sheet_feedback_with_status_key(self):
        with patch(
            "app.services.google_sheets_service.update_sheet_feedback"
        ) as feedback_mock:
            update_sheet_status("https://sheet.example", 5, "do_not_call")

        feedback_mock.assert_called_once_with(
            "https://sheet.example", 5, {"status": "do_not_call"}
        )


class IsSuppressedTests(unittest.TestCase):
    def _conn_with(self, customer_row, suppression_row=None):
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        cursor.fetchone.side_effect = [customer_row, suppression_row]
        return conn

    def test_true_when_customer_flagged_do_not_call(self):
        conn = self._conn_with({
            "do_not_call": True, "is_active": False,
            "organization_id": 1, "phone": "9994146080",
        })
        self.assertTrue(telephony_service.is_suppressed(conn, customer_id=1, organization_id=1))

    def test_true_when_phone_hash_is_in_suppression_list(self):
        conn = self._conn_with(
            {"do_not_call": False, "is_active": True, "organization_id": 1, "phone": "9994146080"},
            suppression_row={"1": 1},
        )
        self.assertTrue(telephony_service.is_suppressed(conn, customer_id=1, organization_id=1, phone_number="9994146080"))

    def test_false_when_neither_flag_nor_list_match(self):
        conn = self._conn_with(
            {"do_not_call": False, "is_active": True, "organization_id": 1, "phone": "9994146080"},
            suppression_row=None,
        )
        self.assertFalse(telephony_service.is_suppressed(conn, customer_id=1, organization_id=1, phone_number="9994146080"))

    def test_false_when_no_phone_available_at_all(self):
        conn = self._conn_with({
            "do_not_call": False, "is_active": True, "organization_id": 1, "phone": "",
        })
        self.assertFalse(telephony_service.is_suppressed(conn, customer_id=1, organization_id=1, phone_number=""))


if __name__ == "__main__":
    unittest.main()
