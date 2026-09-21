import json
import unittest
from unittest.mock import MagicMock, patch

from app.services import call_recording_analysis


class ReanalyzeTransferredCallTests(unittest.TestCase):
    def test_skips_calls_that_were_never_transferred(self):
        db = MagicMock()
        db.cursor.return_value.fetchone.return_value = None
        result = call_recording_analysis.reanalyze_transferred_call(db, 42, 99)
        self.assertFalse(result)
        db.commit.assert_not_called()

    def test_skips_when_recording_is_not_ready_yet(self):
        db = MagicMock()
        cursor = db.cursor.return_value
        cursor.fetchone.side_effect = [
            {"id": 6},  # a completed transfer exists
            {"provider_recording_id": None, "transcript": "", "status": "completed", "call_status": "completed"},
        ]
        result = call_recording_analysis.reanalyze_transferred_call(db, 42, 99)
        self.assertFalse(result)

    @patch("app.services.call_recording_analysis.resolve_openai_api_key", return_value=None)
    def test_skips_when_no_openai_key_is_configured(self, _mock_key):
        db = MagicMock()
        cursor = db.cursor.return_value
        cursor.fetchone.side_effect = [
            {"id": 6},
            {"provider_recording_id": "rec-1", "transcript": "", "status": "completed", "call_status": "completed"},
        ]
        result = call_recording_analysis.reanalyze_transferred_call(db, 42, 99)
        self.assertFalse(result)

    @patch("app.services.call_recording_analysis.crm_outbox_service")
    @patch("app.services.call_recording_analysis.get_telephony_provider")
    @patch("app.services.call_recording_analysis.resolve_openai_api_key", return_value="sk-test")
    @patch("app.services.call_recording_analysis._transcribe", return_value="agent: happy to help, sending you a quote today")
    @patch("app.services.call_recording_analysis.groq_service.analyze_conversation")
    def test_rescoring_updates_transcript_summary_and_lead_tier(
        self, mock_analyze, _mock_transcribe, _mock_key, mock_get_provider, mock_crm_outbox,
    ):
        db = MagicMock()
        cursor = db.cursor.return_value
        updated_row = {
            "id": 99, "organization_id": 42, "qualification": "hot", "lead_score": 85,
        }
        cursor.fetchone.side_effect = [
            {"id": 6},
            {
                "customer_id": 555,
                "provider_recording_id": "rec-1", "transcript": "AI: hello\nCustomer: I need business help",
                "status": "completed", "call_status": "completed",
            },
            updated_row,
        ]
        mock_get_provider.return_value.get_recording.return_value = (b"audio-bytes", "audio/mpeg")
        mock_analyze.return_value = json.dumps({
            "lead_score": 85, "customer_need": "Wants a business quote today",
            "outcome": "Agent agreed to send pricing", "next_action": "Follow up tomorrow",
        })
        result = call_recording_analysis.reanalyze_transferred_call(db, 42, 99)
        self.assertTrue(result)
        update = next(c for c in cursor.execute.call_args_list if "UPDATE call_logs" in c.args[0])
        params = update.args[1]
        self.assertIn("agent: happy to help", params[0])  # full_transcript includes recording text
        self.assertEqual(85, params[3])  # lead_score
        self.assertEqual("hot", params[4])  # qualification derived from score >= 80

        # Verify customer_status is updated for customer_id=555
        customer_update = next(c for c in cursor.execute.call_args_list if "UPDATE customers" in c.args[0])
        self.assertEqual("hot", customer_update.args[1][0])
        self.assertEqual(555, customer_update.args[1][1])
        self.assertEqual(42, customer_update.args[1][2])

        # The corrected result must reach a CRM that may already have the
        # first, rushed classification -- not just update our own database.
        mock_crm_outbox.emit_call_completed.assert_called_once_with(db, updated_row, commit=False)
        db.commit.assert_called_once()

    @patch("app.services.call_recording_analysis.get_telephony_provider")
    @patch("app.services.call_recording_analysis.resolve_openai_api_key", return_value="sk-test")
    def test_provider_failure_is_caught_and_does_not_raise(self, _mock_key, mock_get_provider):
        db = MagicMock()
        cursor = db.cursor.return_value
        cursor.fetchone.side_effect = [
            {"id": 6},
            {"provider_recording_id": "rec-1", "transcript": "", "status": "completed", "call_status": "completed"},
        ]
        mock_get_provider.return_value.get_recording.side_effect = RuntimeError("Plivo recording URL is unavailable")
        result = call_recording_analysis.reanalyze_transferred_call(db, 42, 99)
        self.assertFalse(result)
        db.commit.assert_not_called()

    @patch("time.sleep", return_value=None)
    @patch("app.services.call_recording_analysis.crm_outbox_service")
    @patch("app.services.call_recording_analysis.get_telephony_provider")
    @patch("app.services.call_recording_analysis.resolve_openai_api_key", return_value="sk-test")
    @patch("app.services.call_recording_analysis._transcribe", return_value="agent: resolved problem")
    @patch("app.services.call_recording_analysis.groq_service.analyze_conversation")
    def test_rescores_when_transfer_status_becomes_completed_after_polling(
        self, mock_analyze, _mock_transcribe, _mock_key, mock_get_provider, _mock_crm_outbox, _mock_sleep,
    ):
        db = MagicMock()
        cursor = db.cursor.return_value
        cursor.fetchone.side_effect = [
            {"id": 6, "status": "answered"},  # attempt 1: not completed yet
            {"id": 6, "status": "completed"},  # attempt 2: completed
            {"provider_recording_id": "rec-1", "transcript": "AI: hi", "status": "completed", "call_status": "completed"},
            {"id": 99, "organization_id": 42, "qualification": "warm", "lead_score": 70},
        ]
        mock_get_provider.return_value.get_recording.return_value = (b"audio", "audio/mpeg")
        mock_analyze.return_value = json.dumps({"lead_score": 70, "customer_need": "Needs help"})
        result = call_recording_analysis.reanalyze_transferred_call(db, 42, 99, poll_attempts=3, poll_delay_seconds=0.01)
        self.assertTrue(result)
        db.commit.assert_called_once()

    @patch("app.services.call_recording_analysis.crm_outbox_service")
    @patch("app.services.call_recording_analysis.get_telephony_provider")
    @patch("app.services.call_recording_analysis.resolve_openai_api_key", return_value="sk-test")
    @patch("app.services.call_recording_analysis._transcribe", return_value="agent: closed deal")
    @patch("app.services.call_recording_analysis.groq_service.analyze_conversation")
    def test_rescores_when_transfer_status_is_answered_and_parent_call_is_completed(
        self, mock_analyze, _mock_transcribe, _mock_key, mock_get_provider, _mock_crm_outbox,
    ):
        db = MagicMock()
        cursor = db.cursor.return_value
        cursor.fetchone.side_effect = [
            {"id": 6, "status": "answered"},
            {"status": "completed", "call_status": "completed"},  # parent call check
            {"provider_recording_id": "rec-1", "transcript": "AI: hi", "status": "completed", "call_status": "completed"},
            {"id": 99, "organization_id": 42, "qualification": "hot", "lead_score": 90},
        ]
        mock_get_provider.return_value.get_recording.return_value = (b"audio", "audio/mpeg")
        mock_analyze.return_value = json.dumps({"lead_score": 90, "customer_need": "Purchased course"})
        result = call_recording_analysis.reanalyze_transferred_call(db, 42, 99, poll_attempts=1)
        self.assertTrue(result)
        db.commit.assert_called_once()

    def test_skips_when_call_already_reanalyzed(self):
        db = MagicMock()
        cursor = db.cursor.return_value
        cursor.fetchone.side_effect = [
            {"id": 6, "status": "completed"},
            {
                "provider_recording_id": "rec-1",
                "transcript": "AI: hello\n\n[Full call recording transcript, includes the conversation after human transfer]\nStaff: done",
                "status": "completed",
                "call_status": "completed",
            },
        ]
        result = call_recording_analysis.reanalyze_transferred_call(db, 42, 99)
        self.assertTrue(result)
        db.commit.assert_not_called()

    @patch("app.services.call_recording_analysis.get_telephony_provider")
    @patch("app.services.call_recording_analysis.resolve_openai_api_key", return_value="sk-test")
    def test_skips_when_recording_exceeds_25mb(self, _mock_key, mock_get_provider):
        db = MagicMock()
        cursor = db.cursor.return_value
        cursor.fetchone.side_effect = [
            {"id": 6, "status": "completed"},
            {"provider_recording_id": "rec-huge", "transcript": "", "status": "completed", "call_status": "completed"},
        ]
        # 26 MB dummy audio
        huge_bytes = b"0" * (26 * 1024 * 1024)
        mock_get_provider.return_value.get_recording.return_value = (huge_bytes, "audio/mpeg")
        result = call_recording_analysis.reanalyze_transferred_call(db, 42, 99)
        self.assertFalse(result)
        db.commit.assert_not_called()

    @patch("app.services.call_recording_analysis.requests.post")
    def test_transcribe_passes_multilingual_whisper_hints_tamil(self, mock_post):
        mock_post.return_value.json.return_value = {"text": "வணக்கம், நன்றி"}
        mock_post.return_value.raise_for_status = MagicMock()

        text = call_recording_analysis._transcribe(
            api_key="sk-test",
            audio_bytes=b"sample-audio",
            content_type="audio/mpeg",
            language="ta",
            prompt="DigiDARA AI voice calling, course enquiry, fees, Tamil and English conversation.",
        )
        self.assertEqual("வணக்கம், நன்றி", text)
        mock_post.assert_called_once()
        data_sent = mock_post.call_args[1]["data"]
        self.assertEqual("ta", data_sent["language"])
        self.assertIn("Tamil and English", data_sent["prompt"])

    @patch("app.services.call_recording_analysis.requests.post")
    def test_transcribe_passes_multilingual_whisper_hints_english(self, mock_post):
        mock_post.return_value.json.return_value = {"text": "Hello, thank you"}
        mock_post.return_value.raise_for_status = MagicMock()

        text = call_recording_analysis._transcribe(
            api_key="sk-test",
            audio_bytes=b"sample-audio",
            content_type="audio/mpeg",
            language="en",
            prompt="DigiDARA AI voice calling, course enquiry, admissions and fees conversation.",
        )
        self.assertEqual("Hello, thank you", text)
        mock_post.assert_called_once()
        data_sent = mock_post.call_args[1]["data"]
        self.assertEqual("en", data_sent["language"])
        self.assertIn("admissions and fees", data_sent["prompt"])

    @patch("time.sleep", return_value=None)
    @patch("app.services.call_recording_analysis.requests.post")
    def test_transcribe_retries_transient_failure(self, mock_post, _mock_sleep):
        import requests
        success_mock = MagicMock()
        success_mock.json.return_value = {"text": "Recovered text"}
        success_mock.raise_for_status = MagicMock()

        # Fail on attempt 1 with network error, succeed on attempt 2
        mock_post.side_effect = [
            requests.RequestException("Temporary DNS glitch"),
            success_mock,
        ]

        text = call_recording_analysis._transcribe(
            api_key="sk-test",
            audio_bytes=b"sample-audio",
            content_type="audio/mpeg",
        )
        self.assertEqual("Recovered text", text)
        self.assertEqual(2, mock_post.call_count)


if __name__ == "__main__":
    unittest.main()
