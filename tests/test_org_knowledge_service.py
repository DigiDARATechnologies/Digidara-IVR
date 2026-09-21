"""Tests for organization-scoped knowledge base document management.

Every case uses a mocked db cursor — no real database. Cache invalidation
is verified via mocking, not by touching memory_kb's real module state.
"""

import unittest
from unittest.mock import MagicMock, patch

from app.services import org_knowledge_service


def _mock_db(fetchall_return=None):
    db = MagicMock()
    cursor = MagicMock()
    db.cursor.return_value = cursor
    if fetchall_return is not None:
        cursor.fetchall.return_value = fetchall_return
    return db, cursor


class AddDocumentTests(unittest.TestCase):
    def test_deletes_existing_chunks_then_inserts_new_ones_and_invalidates(self):
        db, cursor = _mock_db()
        with patch.object(org_knowledge_service, "invalidate_org_index") as invalidate_mock:
            chunks_written = org_knowledge_service.add_document(
                db, 42, lang="en", collection="pricing", doc_id="acme_pricing",
                text="Acme charges 999 rupees per month for the standard plan.",
            )
        self.assertEqual(1, chunks_written)

        calls = cursor.execute.call_args_list
        delete_sql, delete_params = calls[0].args
        self.assertIn("DELETE FROM knowledge_chunks", delete_sql)
        self.assertEqual((42, "acme_pricing"), delete_params)

        insert_sql, insert_params = calls[1].args
        self.assertIn("INSERT INTO knowledge_chunks", insert_sql)
        self.assertEqual(42, insert_params[0])
        self.assertEqual("en", insert_params[1])
        self.assertEqual("pricing", insert_params[2])
        self.assertEqual("acme_pricing", insert_params[3])
        self.assertEqual(0, insert_params[4])

        db.commit.assert_called_once()
        invalidate_mock.assert_called_once_with(42, "en")

    def test_long_text_produces_multiple_chunks_each_inserted(self):
        db, cursor = _mock_db()
        long_text = " ".join(f"Sentence number {i} about the product." for i in range(200))
        with patch.object(org_knowledge_service, "invalidate_org_index"):
            chunks_written = org_knowledge_service.add_document(
                db, 1, lang="en", collection="faq", doc_id="big_doc", text=long_text,
            )
        self.assertGreater(chunks_written, 1)
        insert_calls = [c for c in cursor.execute.call_args_list if "INSERT" in c.args[0]]
        self.assertEqual(chunks_written, len(insert_calls))
        chunk_indexes = [c.args[1][4] for c in insert_calls]
        self.assertEqual(list(range(chunks_written)), chunk_indexes)


class DeleteDocumentTests(unittest.TestCase):
    def test_returns_false_and_does_not_delete_when_document_not_found(self):
        db, cursor = _mock_db(fetchall_return=[])
        with patch.object(org_knowledge_service, "invalidate_org_index") as invalidate_mock:
            deleted = org_knowledge_service.delete_document(db, 42, "missing_doc")
        self.assertFalse(deleted)
        delete_calls = [c for c in cursor.execute.call_args_list if "DELETE" in c.args[0]]
        self.assertEqual(0, len(delete_calls))
        invalidate_mock.assert_not_called()

    def test_deletes_and_invalidates_every_language_the_document_existed_in(self):
        db, cursor = _mock_db(fetchall_return=[{"lang": "en"}, {"lang": "ta"}])
        with patch.object(org_knowledge_service, "invalidate_org_index") as invalidate_mock:
            deleted = org_knowledge_service.delete_document(db, 42, "bilingual_doc")
        self.assertTrue(deleted)
        delete_calls = [c for c in cursor.execute.call_args_list if "DELETE" in c.args[0]]
        self.assertEqual(1, len(delete_calls))
        self.assertEqual((42, "bilingual_doc"), delete_calls[0].args[1])
        db.commit.assert_called_once()
        self.assertEqual(
            [(42, "en"), (42, "ta")],
            [c.args for c in invalidate_mock.call_args_list],
        )

    def test_only_deletes_within_the_caller_organization(self):
        db, cursor = _mock_db(fetchall_return=[{"lang": "en"}])
        with patch.object(org_knowledge_service, "invalidate_org_index"):
            org_knowledge_service.delete_document(db, 99, "someone_elses_doc")
        select_sql, select_params = cursor.execute.call_args_list[0].args
        self.assertEqual((99, "someone_elses_doc"), select_params)


class ListDocumentsTests(unittest.TestCase):
    def test_scopes_the_query_to_the_given_organization(self):
        rows = [{"doc_id": "d1", "lang": "en", "collection": "faq", "chunk_count": 2, "updated_at": None}]
        db, cursor = _mock_db(fetchall_return=rows)
        result = org_knowledge_service.list_documents(db, 42)
        self.assertEqual(rows, result)
        sql, params = cursor.execute.call_args.args
        self.assertIn("organization_id=%s", sql)
        self.assertEqual((42,), params)


class ExtractTextFromFileTests(unittest.TestCase):
    def test_extracts_text_from_a_real_docx(self):
        import io

        from docx import Document

        doc = Document()
        doc.add_paragraph("Acme Test Co refunds within 45 days.")
        buf = io.BytesIO()
        doc.save(buf)

        text = org_knowledge_service.extract_text_from_file("policy.docx", buf.getvalue())
        self.assertIn("Acme Test Co refunds within 45 days.", text)

    def test_extracts_text_from_a_plain_txt_file(self):
        text = org_knowledge_service.extract_text_from_file("notes.txt", b"Plain text content.")
        self.assertEqual("Plain text content.", text)

    def test_extracts_text_from_a_real_pdf(self):
        import io

        from pypdf import PdfWriter

        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        buf = io.BytesIO()
        writer.write(buf)

        # A blank page has no extractable text, but this proves the PDF
        # parsing path runs cleanly against a real, well-formed PDF.
        text = org_knowledge_service.extract_text_from_file("doc.pdf", buf.getvalue())
        self.assertEqual("", text)

    def test_rejects_an_unsupported_extension(self):
        with self.assertRaises(ValueError):
            org_knowledge_service.extract_text_from_file("image.png", b"\x89PNG")

    def test_rejects_a_corrupt_pdf(self):
        with self.assertRaises(Exception):
            org_knowledge_service.extract_text_from_file("broken.pdf", b"not actually a pdf")


if __name__ == "__main__":
    unittest.main()
