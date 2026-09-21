"""Tests for Excel/CSV upload parsing and the upload-batch queue adapter."""

import io
import unittest
from unittest.mock import MagicMock, patch

from app.services import bulk_upload_service


class IsUploadReferenceTests(unittest.TestCase):
    def test_recognizes_upload_prefixed_reference(self):
        self.assertTrue(bulk_upload_service.is_upload_reference("upload:abc-123"))

    def test_real_sheet_url_is_not_an_upload_reference(self):
        self.assertFalse(
            bulk_upload_service.is_upload_reference("https://docs.google.com/spreadsheets/d/xyz")
        )

    def test_blank_or_none_is_not_an_upload_reference(self):
        self.assertFalse(bulk_upload_service.is_upload_reference(""))
        self.assertFalse(bulk_upload_service.is_upload_reference(None))


class ParseFileTests(unittest.TestCase):
    def test_parses_csv_with_phone_no_header_variant(self):
        content = "Name,Phone no,Course\nRanjeeth,9994146080,AI Course\n".encode()
        rows = bulk_upload_service.parse_file("leads.csv", content)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "Ranjeeth")
        self.assertEqual(rows[0]["phone"], "9994146080")
        self.assertEqual(rows[0]["investigated_course"], "AI Course")
        self.assertEqual(rows[0]["row_number"], 2)

    def test_parses_xlsx(self):
        from openpyxl import Workbook

        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Name", "Phone", "Language"])
        sheet.append(["Hema", "6380353710", "tamil"])
        buffer = io.BytesIO()
        workbook.save(buffer)

        rows = bulk_upload_service.parse_file("leads.xlsx", buffer.getvalue())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["phone"], "6380353710")
        self.assertEqual(rows[0]["language"], "tamil")

    def test_rejects_unsupported_extension(self):
        with self.assertRaises(ValueError):
            bulk_upload_service.parse_file("leads.pdf", b"not a real file")

    def test_empty_file_returns_no_rows(self):
        self.assertEqual(bulk_upload_service.parse_file("leads.csv", b""), [])

    def test_rows_without_a_phone_number_are_still_parsed_but_flaggable(self):
        content = "Name,Phone,Course\nNo Phone Person,,AI Course\n".encode()
        rows = bulk_upload_service.parse_file("leads.csv", content)
        self.assertEqual(rows[0]["phone"], "")


class CreateBatchTests(unittest.TestCase):
    def test_skips_rows_with_no_phone_and_returns_upload_reference(self):
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        rows = [
            {"row_number": 2, "name": "A", "phone": "9000000001"},
            {"row_number": 3, "name": "B", "phone": ""},
        ]
        reference = bulk_upload_service.create_batch(conn, 1, 5, "leads.csv", rows)
        self.assertTrue(reference.startswith(bulk_upload_service.UPLOAD_PREFIX))
        self.assertEqual(cursor.execute.call_count, 1)
        conn.commit.assert_called_once()


class ReadAndUpdateRowsTests(unittest.TestCase):
    def test_read_rows_shapes_output_like_sheet_rows(self):
        fake_db = MagicMock()
        fake_cursor = MagicMock()
        fake_db.cursor.return_value = fake_cursor
        fake_cursor.fetchall.return_value = [
            {"row_index": 2, "name": "A", "phone": "9000000001", "language": "english",
             "status": "queue", "investigated_course": "", "internship_or_course": "", "course_duration": ""}
        ]
        with patch("app.database.db.get_db_connection", return_value=fake_db):
            rows = bulk_upload_service.read_rows("upload:test-id")
        self.assertEqual(rows[0]["row_number"], 2)
        self.assertEqual(rows[0]["status"], "queue")
        fake_db.close.assert_called_once()

    def test_update_status_scopes_to_upload_id_and_row(self):
        fake_db = MagicMock()
        fake_cursor = MagicMock()
        fake_db.cursor.return_value = fake_cursor
        with patch("app.database.db.get_db_connection", return_value=fake_db):
            bulk_upload_service.update_status("upload:test-id", 2, "ongoing")
        args = fake_cursor.execute.call_args[0][1]
        self.assertEqual(args, ("ongoing", "test-id", 2))
        fake_db.commit.assert_called_once()

    def test_update_feedback_only_writes_when_status_present(self):
        with patch.object(bulk_upload_service, "update_status") as update_mock:
            bulk_upload_service.update_feedback("upload:test-id", 2, {"summary": "no status here"})
        update_mock.assert_not_called()

        with patch.object(bulk_upload_service, "update_status") as update_mock:
            bulk_upload_service.update_feedback("upload:test-id", 2, {"status": "completed"})
        update_mock.assert_called_once_with("upload:test-id", 2, "completed")


if __name__ == "__main__":
    unittest.main()
