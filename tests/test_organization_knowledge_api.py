"""Tests for the /organization-knowledge-base API endpoints.

Route functions are called directly (matching this repo's convention for
FastAPI route-level tests), with org_knowledge_service mocked out.
"""

import asyncio
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app.api import organization_knowledge as api


class _FakeUpload:
    def __init__(self, filename: str, content: bytes):
        self.filename = filename
        self._content = content

    async def read(self) -> bytes:
        return self._content


def _run(coro):
    return asyncio.run(coro)


class ListDocumentsTests(unittest.TestCase):
    def test_returns_documents_for_the_caller_organization(self):
        db = MagicMock()
        with patch.object(
            api.org_knowledge_service, "list_documents",
            return_value=[{"doc_id": "d1", "lang": "en", "collection": "faq",
                           "chunk_count": 2, "updated_at": "2026-08-09 10:00:00"}],
        ) as list_mock:
            result = api.list_documents(admin={"organization_id": 42}, db=db)
        list_mock.assert_called_once_with(db, 42)
        self.assertEqual(1, len(result))
        self.assertEqual("d1", result[0].doc_id)


class AddDocumentTests(unittest.TestCase):
    def test_rejects_when_neither_text_nor_file_is_given(self):
        with self.assertRaises(HTTPException) as raised:
            _run(api.add_document(
                collection="faq", doc_id="d1", lang="en", text="   ", file=None,
                admin={"organization_id": 42}, db=MagicMock(),
            ))
        self.assertEqual(422, raised.exception.status_code)

    def test_rejects_unsupported_language(self):
        with self.assertRaises(HTTPException) as raised:
            _run(api.add_document(
                collection="faq", doc_id="d1", lang="fr", text="hello", file=None,
                admin={"organization_id": 42}, db=MagicMock(),
            ))
        self.assertEqual(422, raised.exception.status_code)

    def test_scopes_the_write_to_the_caller_organization(self):
        with patch.object(api.org_knowledge_service, "add_document", return_value=3) as add_mock:
            result = _run(api.add_document(
                collection="pricing", doc_id="acme_pricing", lang="en",
                text="Acme charges 999/mo.", file=None,
                admin={"organization_id": 42}, db=MagicMock(),
            ))
        add_mock.assert_called_once()
        args, kwargs = add_mock.call_args
        self.assertEqual(42, args[1])
        self.assertEqual("en", kwargs["lang"])
        self.assertEqual("pricing", kwargs["collection"])
        self.assertEqual("acme_pricing", kwargs["doc_id"])
        self.assertEqual(3, result.chunks_inserted)

    def test_normalizes_language_casing(self):
        with patch.object(api.org_knowledge_service, "add_document", return_value=1) as add_mock:
            _run(api.add_document(
                collection="faq", doc_id="d1", lang="EN", text="hello", file=None,
                admin={"organization_id": 42}, db=MagicMock(),
            ))
        self.assertEqual("en", add_mock.call_args.kwargs["lang"])

    def test_extracts_text_from_an_uploaded_file_when_no_text_is_pasted(self):
        upload = _FakeUpload("policy.txt", b"Refunds within 45 days.")
        with patch.object(api.org_knowledge_service, "add_document", return_value=1) as add_mock:
            _run(api.add_document(
                collection="policies", doc_id="refund", lang="en", text="", file=upload,
                admin={"organization_id": 42}, db=MagicMock(),
            ))
        self.assertEqual("Refunds within 45 days.", add_mock.call_args.kwargs["text"])

    def test_combines_pasted_text_and_uploaded_file_text(self):
        upload = _FakeUpload("policy.txt", b"Refunds within 45 days.")
        with patch.object(api.org_knowledge_service, "add_document", return_value=1) as add_mock:
            _run(api.add_document(
                collection="policies", doc_id="refund", lang="en", text="See below:", file=upload,
                admin={"organization_id": 42}, db=MagicMock(),
            ))
        combined = add_mock.call_args.kwargs["text"]
        self.assertIn("See below:", combined)
        self.assertIn("Refunds within 45 days.", combined)

    def test_rejects_an_unsupported_file_type_as_422_not_500(self):
        upload = _FakeUpload("photo.png", b"\x89PNG\r\n")
        with self.assertRaises(HTTPException) as raised:
            _run(api.add_document(
                collection="faq", doc_id="d1", lang="en", text="", file=upload,
                admin={"organization_id": 42}, db=MagicMock(),
            ))
        self.assertEqual(422, raised.exception.status_code)

    def test_a_corrupt_file_of_a_supported_type_is_422_not_500(self):
        upload = _FakeUpload("broken.pdf", b"not actually a pdf")
        with self.assertRaises(HTTPException) as raised:
            _run(api.add_document(
                collection="faq", doc_id="d1", lang="en", text="", file=upload,
                admin={"organization_id": 42}, db=MagicMock(),
            ))
        self.assertEqual(422, raised.exception.status_code)


class DeleteDocumentTests(unittest.TestCase):
    def test_scopes_the_delete_to_the_caller_organization(self):
        db = MagicMock()
        with patch.object(api.org_knowledge_service, "delete_document", return_value=True) as delete_mock:
            result = api.delete_document("acme_pricing", admin={"organization_id": 42}, db=db)
        delete_mock.assert_called_once_with(db, 42, "acme_pricing")
        self.assertTrue(result.deleted)


if __name__ == "__main__":
    unittest.main()
