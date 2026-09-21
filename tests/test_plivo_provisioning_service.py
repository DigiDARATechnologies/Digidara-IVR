"""Tests for automated Plivo India number provisioning.

Every Plivo SDK call is mocked — nothing in this file makes a real network
request, and in particular nothing here ever calls the real numbers.buy(),
which has a real recurring cost on the live account.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services import plivo_provisioning_service as provisioning


def _conn_with(fetchone_result=None):
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value = cursor
    cursor.fetchone.return_value = fetchone_result
    return conn, cursor


class GetComplianceRequirementsTests(unittest.TestCase):
    def test_passes_business_user_type_and_returns_dict(self):
        fake_client = MagicMock()
        fake_client.phone_number_compliance_requirements.get.return_value = SimpleNamespace(
            country_iso="IN", document_types=[]
        )
        with patch.object(provisioning, "_main_account_client", return_value=fake_client):
            result = provisioning.get_compliance_requirements()
        fake_client.phone_number_compliance_requirements.get.assert_called_once_with(
            country_iso="IN", number_type="local", user_type="business",
        )
        self.assertEqual(result["country_iso"], "IN")


class SubmitComplianceApplicationTests(unittest.TestCase):
    def test_rejects_mismatched_document_lists(self):
        conn, _cursor = _conn_with()
        with self.assertRaises(ValueError):
            provisioning.submit_compliance_application(
                conn, 1, business_name="Acme", business_email="a@acme.in",
                address_line1="1 MG Road", city="Bangalore", state="Karnataka",
                postal_code="560001", registration_number="U1234",
                document_type_ids=["a", "b"], document_paths=["/tmp/a.pdf"],
                callback_url="https://example.test/callback",
            )

    def test_submits_and_records_the_application(self):
        conn, cursor = _conn_with()
        fake_client = MagicMock()
        fake_client.phone_number_compliance.create.return_value = SimpleNamespace(
            compliance_id="abc-123", status="pending"
        )
        with patch.object(provisioning, "_main_account_client", return_value=fake_client):
            result = provisioning.submit_compliance_application(
                conn, 7, business_name="Acme Pvt Ltd", business_email="a@acme.in",
                address_line1="1 MG Road", city="Bangalore", state="Karnataka",
                postal_code="560001", registration_number="U1234",
                document_type_ids=["doc-type-1"], document_paths=["/tmp/a.pdf"],
                callback_url="https://example.test/callback",
            )
        self.assertEqual(result["compliance_id"], "abc-123")
        create_kwargs = fake_client.phone_number_compliance.create.call_args.kwargs
        self.assertEqual(create_kwargs["data"]["end_user"]["name"], "Acme Pvt Ltd")
        self.assertEqual(create_kwargs["data"]["callback_url"], "https://example.test/callback")
        self.assertEqual(create_kwargs["documents"], ["/tmp/a.pdf"])
        insert_sql, insert_values = cursor.execute.call_args.args
        self.assertIn("INSERT INTO plivo_compliance_applications", insert_sql)
        self.assertEqual(insert_values[0], 7)
        self.assertEqual(insert_values[1], "abc-123")
        conn.commit.assert_called_once()

    def test_wraps_plivo_failure_as_provisioning_error(self):
        conn, _cursor = _conn_with()
        fake_client = MagicMock()
        fake_client.phone_number_compliance.create.side_effect = RuntimeError("boom")
        with patch.object(provisioning, "_main_account_client", return_value=fake_client):
            with self.assertRaises(provisioning.ProvisioningError):
                provisioning.submit_compliance_application(
                    conn, 1, business_name="Acme", business_email="a@acme.in",
                    address_line1="x", city="x", state="x", postal_code="x",
                    registration_number="x", document_type_ids=["d1"],
                    document_paths=["/tmp/a.pdf"], callback_url="https://example.test",
                )


class HandleComplianceWebhookTests(unittest.TestCase):
    def test_updates_status_and_returns_the_row(self):
        conn, cursor = _conn_with(fetchone_result={"id": 1, "status": "accepted"})
        result = provisioning.handle_compliance_webhook(
            conn, {"compliance_id": "abc-123", "status": "accepted"}
        )
        update_sql, update_values = cursor.execute.call_args_list[0].args
        self.assertIn("UPDATE plivo_compliance_applications", update_sql)
        self.assertEqual(update_values[0], "accepted")
        self.assertEqual(update_values[2], "abc-123")
        self.assertEqual(result["status"], "accepted")

    def test_ignores_payload_missing_compliance_id_or_status(self):
        conn, cursor = _conn_with()
        self.assertIsNone(provisioning.handle_compliance_webhook(conn, {"status": "accepted"}))
        self.assertIsNone(provisioning.handle_compliance_webhook(conn, {"compliance_id": "abc"}))
        cursor.execute.assert_not_called()


class SearchNumbersTests(unittest.TestCase):
    def test_rejects_unsupported_prefix(self):
        with self.assertRaises(provisioning.ProvisioningError):
            provisioning.search_numbers("160")

    def test_maps_prefix_to_city_and_shapes_results(self):
        fake_number = MagicMock(number="918031452648", city="Bangalore",
                                 region="Bangalore", monthly_rental_rate="250.00", voice_rate="0.01")
        fake_client = MagicMock()
        fake_client.numbers.search.return_value = [fake_number]
        with patch.object(provisioning, "_main_account_client", return_value=fake_client):
            results = provisioning.search_numbers("080")
        fake_client.numbers.search.assert_called_once_with(
            country_iso="IN", type="fixed", city="Bangalore", limit=10,
        )
        self.assertEqual(results[0]["number"], "918031452648")


class EnsureSubaccountTests(unittest.TestCase):
    def test_returns_existing_credential_without_creating_a_new_subaccount(self):
        conn = MagicMock()
        with patch.object(
            provisioning.tenant_credentials_service, "get_credential",
            return_value={"auth_id": "SAXXXX", "auth_token": "tok"},
        ), patch.object(provisioning, "_main_account_client") as client_factory:
            result = provisioning._ensure_subaccount(conn, 1)
        client_factory.assert_not_called()
        self.assertEqual(result["auth_id"], "SAXXXX")

    def test_creates_and_stores_a_new_subaccount_when_none_exists(self):
        conn = MagicMock()
        fake_client = MagicMock()
        fake_client.subaccounts.create.return_value = SimpleNamespace(
            auth_id="SANEW1", auth_token="new-token"
        )
        with patch.object(provisioning.tenant_credentials_service, "get_credential", return_value=None), \
             patch.object(provisioning.tenant_credentials_service, "set_credential") as set_mock, \
             patch.object(provisioning, "_main_account_client", return_value=fake_client):
            result = provisioning._ensure_subaccount(conn, 3)
        fake_client.subaccounts.create.assert_called_once_with(name="digidara-org-3", enabled=True)
        set_mock.assert_called_once_with(conn, 3, "plivo", {"auth_id": "SANEW1", "auth_token": "new-token"})
        self.assertEqual(result["auth_id"], "SANEW1")


class ProvisionNumberTests(unittest.TestCase):
    def test_buys_and_assigns_the_exact_chosen_number(self):
        conn, cursor = _conn_with()
        fake_client = MagicMock()
        with patch.object(
            provisioning, "_ensure_subaccount",
            return_value={"auth_id": "SAXXXX", "auth_token": "tok"},
        ), patch.object(provisioning, "_main_account_client", return_value=fake_client), \
           patch.object(provisioning.tenant_credentials_service, "get_credential", return_value={}), \
           patch.object(provisioning.tenant_credentials_service, "set_credential") as set_mock:
            result = provisioning.provision_number(conn, 3, "918031452648", "compliance-abc")

        fake_client.numbers.buy.assert_called_once_with(
            number="918031452648", compliance_application_id="compliance-abc",
        )
        fake_client.numbers.update.assert_called_once_with(
            number="918031452648", subaccount="SAXXXX",
        )
        set_mock.assert_called_once()
        self.assertEqual(result["number"], "918031452648")
        self.assertEqual(result["subaccount_auth_id"], "SAXXXX")
        conn.commit.assert_called()

    def test_wraps_buy_failure_as_provisioning_error(self):
        conn, _cursor = _conn_with()
        fake_client = MagicMock()
        fake_client.numbers.buy.side_effect = RuntimeError("insufficient balance")
        with patch.object(
            provisioning, "_ensure_subaccount",
            return_value={"auth_id": "SAXXXX", "auth_token": "tok"},
        ), patch.object(provisioning, "_main_account_client", return_value=fake_client):
            with self.assertRaises(provisioning.ProvisioningError):
                provisioning.provision_number(conn, 3, "918031452648", "compliance-abc")


if __name__ == "__main__":
    unittest.main()
