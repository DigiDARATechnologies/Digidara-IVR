"""Tests for PATCH /organizations/me — lets an admin rename their own
organization, which now flows straight into what the AI says on live calls
(conversation_policy_service's greeting/system-prompt builders)."""

import unittest
from unittest.mock import MagicMock

from app.api.auth import OrganizationUpdateInput, update_organization


class UpdateOrganizationTests(unittest.TestCase):
    def test_updates_only_the_callers_own_organization(self):
        db = MagicMock()
        cursor = MagicMock()
        db.cursor.return_value = cursor
        admin = {"organization_id": 42, "id": 7}

        result = update_organization(
            OrganizationUpdateInput(name="Acme Corp"), admin=admin, db=db,
        )

        update_call = cursor.execute.call_args_list[0]
        update_sql, update_params = update_call.args
        self.assertIn("UPDATE organizations", update_sql)
        self.assertEqual(("Acme Corp", 42), update_params)
        self.assertEqual({"organization_name": "Acme Corp"}, result)

    def test_records_an_audit_log_entry(self):
        db = MagicMock()
        cursor = MagicMock()
        db.cursor.return_value = cursor
        admin = {"organization_id": 42, "id": 7}

        update_organization(OrganizationUpdateInput(name="Acme Corp"), admin=admin, db=db)

        audit_call = cursor.execute.call_args_list[1]
        audit_sql, audit_params = audit_call.args
        self.assertIn("INSERT INTO audit_logs", audit_sql)
        self.assertEqual((42, 7, "42"), audit_params)
        db.commit.assert_called_once()

    def test_strips_surrounding_whitespace(self):
        db = MagicMock()
        cursor = MagicMock()
        db.cursor.return_value = cursor
        admin = {"organization_id": 1, "id": 1}

        result = update_organization(
            OrganizationUpdateInput(name="  Acme Corp  "), admin=admin, db=db,
        )
        self.assertEqual("Acme Corp", result["organization_name"])

    def test_rejects_a_name_shorter_than_two_characters(self):
        with self.assertRaises(Exception):
            OrganizationUpdateInput(name="A")


if __name__ == "__main__":
    unittest.main()
