"""Tests for the /provisioning/plivo API endpoints.

Every provisioning-service call is mocked here too; these tests check request
handling (validation, admin scoping, temp-file cleanup), not real Plivo I/O.
"""

import asyncio
import os
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app.api import provisioning
from app.services.plivo_provisioning_service import ProvisioningError


class _FakeUpload:
    def __init__(self, filename: str, content: bytes):
        self.filename = filename
        self._content = content

    async def read(self) -> bytes:
        return self._content


def _run(coro):
    return asyncio.run(coro)


class RequirementsAndStatusTests(unittest.TestCase):
    def test_requirements_translates_provisioning_error_to_http_502(self):
        with patch.object(provisioning.provisioning, "get_compliance_requirements",
                           side_effect=ProvisioningError("boom")):
            with self.assertRaises(HTTPException) as raised:
                provisioning.requirements(admin={"organization_id": 1})
        self.assertEqual(502, raised.exception.status_code)

    def test_status_reports_not_started_when_no_application_exists(self):
        with patch.object(provisioning.provisioning, "get_latest_application", return_value=None):
            result = provisioning.status(admin={"organization_id": 1}, db=MagicMock())
        self.assertEqual({"status": "not_started"}, result)

    def test_status_returns_the_stored_application(self):
        with patch.object(
            provisioning.provisioning, "get_latest_application",
            return_value={"status": "accepted", "provisioned_number": "918031452648"},
        ):
            result = provisioning.status(admin={"organization_id": 1}, db=MagicMock())
        self.assertEqual("accepted", result["status"])


class SubmitComplianceTests(unittest.TestCase):
    def test_rejects_mismatched_document_type_count(self):
        with self.assertRaises(HTTPException) as raised:
            _run(provisioning.submit_compliance(
                business_name="Acme", business_email="a@acme.in", address_line1="x",
                city="Bangalore", state="Karnataka", postal_code="560001",
                registration_number="U1234", document_type_ids="doc-1,doc-2",
                documents=[_FakeUpload("a.pdf", b"x")],
                admin={"organization_id": 1}, db=MagicMock(),
            ))
        self.assertEqual(422, raised.exception.status_code)

    def test_rejects_when_webhook_base_url_is_not_configured(self):
        with patch.dict(os.environ, {"WEBHOOK_BASE_URL": ""}):
            with self.assertRaises(HTTPException) as raised:
                _run(provisioning.submit_compliance(
                    business_name="Acme", business_email="a@acme.in", address_line1="x",
                    city="Bangalore", state="Karnataka", postal_code="560001",
                    registration_number="U1234", document_type_ids="doc-1",
                    documents=[_FakeUpload("a.pdf", b"x")],
                    admin={"organization_id": 1}, db=MagicMock(),
                ))
        self.assertEqual(503, raised.exception.status_code)

    def test_submits_with_saved_temp_files_and_cleans_them_up(self):
        captured_paths = []

        def fake_submit(db, organization_id, **kwargs):
            captured_paths.extend(kwargs["document_paths"])
            self.assertTrue(all(os.path.exists(p) for p in captured_paths))
            self.assertEqual(1, organization_id)
            self.assertEqual(
                f"https://example.test/api/plivo/compliance-webhook", kwargs["callback_url"],
            )
            return {"compliance_id": "abc-123"}

        with patch.dict(os.environ, {"WEBHOOK_BASE_URL": "https://example.test"}), \
             patch.object(provisioning.provisioning, "submit_compliance_application", side_effect=fake_submit):
            result = _run(provisioning.submit_compliance(
                business_name="Acme", business_email="a@acme.in", address_line1="x",
                city="Bangalore", state="Karnataka", postal_code="560001",
                registration_number="U1234", document_type_ids="doc-1",
                documents=[_FakeUpload("a.pdf", b"file-bytes")],
                admin={"organization_id": 1}, db=MagicMock(),
            ))
        self.assertEqual({"compliance_id": "abc-123"}, result)
        self.assertTrue(captured_paths)
        self.assertFalse(os.path.exists(captured_paths[0]))

    def test_cleans_up_temp_files_even_when_submission_fails(self):
        captured_paths = []

        def fake_submit(db, organization_id, **kwargs):
            captured_paths.extend(kwargs["document_paths"])
            raise ProvisioningError("plivo said no")

        with patch.dict(os.environ, {"WEBHOOK_BASE_URL": "https://example.test"}), \
             patch.object(provisioning.provisioning, "submit_compliance_application", side_effect=fake_submit):
            with self.assertRaises(HTTPException) as raised:
                _run(provisioning.submit_compliance(
                    business_name="Acme", business_email="a@acme.in", address_line1="x",
                    city="Bangalore", state="Karnataka", postal_code="560001",
                    registration_number="U1234", document_type_ids="doc-1",
                    documents=[_FakeUpload("a.pdf", b"file-bytes")],
                    admin={"organization_id": 1}, db=MagicMock(),
                ))
        self.assertEqual(502, raised.exception.status_code)
        self.assertTrue(captured_paths)
        self.assertFalse(os.path.exists(captured_paths[0]))


class SearchAndBuyNumberTests(unittest.TestCase):
    def test_search_numbers_wraps_provisioning_error_as_http_400(self):
        with patch.object(provisioning.provisioning, "search_numbers", side_effect=ProvisioningError("bad prefix")):
            with self.assertRaises(HTTPException) as raised:
                provisioning.search_numbers(prefix="160", admin={"organization_id": 1})
        self.assertEqual(400, raised.exception.status_code)

    def test_search_numbers_returns_wrapped_list(self):
        with patch.object(provisioning.provisioning, "search_numbers", return_value=[{"number": "918031452648"}]):
            result = provisioning.search_numbers(prefix="080", admin={"organization_id": 1})
        self.assertEqual({"numbers": [{"number": "918031452648"}]}, result)

    def test_buy_number_scopes_purchase_to_the_caller_organization(self):
        with patch.object(provisioning.provisioning, "provision_number") as provision_mock:
            provision_mock.return_value = {"number": "918031452648", "subaccount_auth_id": "SAXXXX"}
            db = MagicMock()
            result = provisioning.buy_number(
                number="918031452648", compliance_application_id="compliance-abc",
                admin={"organization_id": 9}, db=db,
            )
        provision_mock.assert_called_once_with(db, 9, "918031452648", "compliance-abc")
        self.assertEqual("918031452648", result["number"])

    def test_buy_number_wraps_provisioning_error_as_http_502(self):
        with patch.object(provisioning.provisioning, "provision_number", side_effect=ProvisioningError("no balance")):
            with self.assertRaises(HTTPException) as raised:
                provisioning.buy_number(
                    number="918031452648", compliance_application_id="compliance-abc",
                    admin={"organization_id": 9}, db=MagicMock(),
                )
        self.assertEqual(502, raised.exception.status_code)


if __name__ == "__main__":
    unittest.main()
