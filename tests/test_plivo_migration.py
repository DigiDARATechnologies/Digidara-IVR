import base64
import os
import unittest
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from app.services import call_log_service
from app.services.telephony.status import map_plivo_status
from app.services.plivo_stream import (
    checkpoint,
    build_answer_xml,
    build_direct_dial_xml,
    build_ivr_prompt_xml,
    build_language_prompt_xml,
    clear_audio,
    media_payload,
    parse_start,
    play_audio,
    stream_token,
    validate_stream_token,
    websocket_signature_url,
)
from app.services.telephony.plivo_provider import PlivoProvider


class PlivoProtocolTests(unittest.TestCase):
    def test_websocket_signature_uses_https_upgrade_url(self):
        self.assertEqual(
            websocket_signature_url(
                "wss://voice.example.com/",
                "/ws/plivo/media",
                "customer_id=1&token=abc",
            ),
            "https://voice.example.com/ws/plivo/media?customer_id=1&token=abc",
        )
        self.assertEqual(
            websocket_signature_url(
                "ws://localhost:8000", "/ws/plivo/media", ""
            ),
            "http://localhost:8000/ws/plivo/media",
        )

    def test_start_and_media_match_plivo_contract(self):
        event = {
            "event": "start",
            "start": {"callId": "call-1", "streamId": "stream-1"},
        }
        self.assertEqual(parse_start(event), ("call-1", "stream-1"))
        self.assertEqual(media_payload({"media": {"payload": "YWJj"}}), "YWJj")

    def test_outbound_audio_and_barge_in_frames(self):
        payload = base64.b64encode(b"\xff" * 160).decode()
        self.assertEqual(
            play_audio(payload),
            {
                "event": "playAudio",
                "media": {
                    "contentType": "audio/x-mulaw",
                    "sampleRate": 8000,
                    "payload": payload,
                },
            },
        )
        self.assertEqual(
            clear_audio("stream-1"),
            {"event": "clearAudio", "streamId": "stream-1"},
        )
        self.assertEqual(
            checkpoint("stream-1", "turn-1"),
            {"event": "checkpoint", "streamId": "stream-1", "name": "turn-1"},
        )

    def test_stream_token_is_bound_to_call_context(self):
        with patch.dict(os.environ, {"PLIVO_STREAM_TOKEN_SECRET": "test-secret"}):
            token = stream_token(10, 20, "abc")
            self.assertTrue(validate_stream_token(token, 10, 20, "abc"))
            self.assertFalse(validate_stream_token(token, 11, 20, "abc"))

    def test_answer_xml_has_recording_stream_and_no_second_voice(self):
        xml = build_answer_xml(
            "wss://voice.test/ws/plivo/media?a=1&b=2",
            "https://voice.test/recording?c=3",
            "https://voice.test/stream-status?c=3",
        )
        self.assertIn('recordSession="true"', xml)
        self.assertIn('recordChannelType="stereo"', xml)
        self.assertIn('maxLength="14400"', xml)
        self.assertIn('playBeep="false"', xml)
        self.assertIn('bidirectional="true"', xml)
        self.assertIn('contentType="audio/x-mulaw;rate=8000"', xml)
        self.assertIn("&amp;", xml)
        self.assertNotIn("<Speak", xml)

    def test_language_prompt_offers_digits_and_falls_through_to_stream(self):
        xml = build_language_prompt_xml(
            "https://voice.test/language-select?a=1&b=2",
            "https://voice.test/language-prompt.mp3",
            "wss://voice.test/ws/plivo/media?a=1&b=2",
            "https://voice.test/recording?c=3",
            "https://voice.test/stream-status?c=3",
        )
        self.assertIn("<GetDigits", xml)
        self.assertIn('numDigits="1"', xml)
        self.assertIn("action=", xml)
        # Plivo's native <Speak> has no Tamil voice, so the menu must be a
        # pre-rendered clip played via <Play>, not provider TTS.
        self.assertIn("<Play>https://voice.test/language-prompt.mp3</Play>", xml)
        self.assertNotIn("<Speak", xml)
        # Same Record/Stream verbs as build_answer_xml must follow, as the
        # fallback path Plivo takes on a GetDigits timeout.
        self.assertIn('recordSession="true"', xml)
        self.assertIn("bidirectional=\"true\"", xml)

    def test_configurable_ivr_uses_audio_and_falls_through_to_stream(self):
        xml = build_ivr_prompt_xml(
            "https://voice.test/ivr-select?a=1", "https://voice.test/ivr-prompt.wav?t=1",
            "wss://voice.test/ws/plivo/media?a=1", "https://voice.test/recording?c=3",
            "https://voice.test/stream-status?c=3", timeout_seconds=7,
            speech_hints="Business, Support, Education", language_code="en-US",
        )
        self.assertIn("<GetInput", xml)
        self.assertNotIn("<GetDigits", xml)
        self.assertIn('inputType="dtmf speech"', xml)
        self.assertIn('executionTimeout="7"', xml)
        self.assertIn('hints="Business, Support, Education"', xml)
        self.assertIn('language="en-US"', xml)
        self.assertIn("ivr-select", xml)
        self.assertIn("ivr-prompt.wav", xml)
        self.assertIn('bidirectional="true"', xml)
        self.assertNotIn("<Speak", xml)

    def test_direct_dial_xml_rings_a_human_with_no_ai_stream_at_all(self):
        xml = build_direct_dial_xml(
            "https://voice.test/ivr-dial-action?a=1", "https://voice.test/transfer-confirm.wav",
            "+919876500000",
        )
        self.assertIn("<Dial", xml)
        self.assertIn('confirmKey="1"', xml)
        self.assertIn("<Number>+919876500000</Number>", xml)
        self.assertIn("ivr-dial-action", xml)
        self.assertIn("transfer-confirm.wav", xml)
        # No AI leg at all for this route: no Stream/Record verbs.
        self.assertNotIn("<Stream", xml)
        self.assertNotIn("<Record", xml)


class StatusMappingTests(unittest.TestCase):
    def test_plivo_states_normalize_to_product_states(self):
        cases = {
            "ringing": "ringing",
            "in-progress": "in-progress",
            "completed": "completed",
            "busy": "busy",
            "no_answer": "no-answer",
            "cancel": "canceled",
            "failed": "failed",
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(map_plivo_status(source), expected)
        self.assertEqual(map_plivo_status("completed", "NO_ANSWER"), "no-answer")
        self.assertEqual(map_plivo_status("completed", "USER_BUSY"), "busy")
        self.assertEqual(map_plivo_status("completed", "CALL_REJECTED"), "failed")
        self.assertEqual(map_plivo_status("ANSWER", "Error Reaching Answer URL"), "failed")
        self.assertEqual(map_plivo_status("ANSWER", "Normal Hangup"), "completed")

    def test_callback_claims_are_idempotent(self):
        source = Path("app/api/plivo.py").read_text(encoding="utf-8")
        self.assertIn("INSERT IGNORE INTO provider_callback_events", source)


class SelectedLanguagePersistenceTests(unittest.TestCase):
    def test_dtmf_language_updates_customer_and_current_call(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value

        call_log_service.update_selected_language(
            connection,
            call_log_id=42,
            organization_id=7,
            customer_id=11,
            language="tamil",
        )

        self.assertEqual(cursor.execute.call_count, 2)
        customer_sql, customer_values = cursor.execute.call_args_list[0].args
        call_sql, call_values = cursor.execute.call_args_list[1].args
        self.assertIn("organization_id=%s", customer_sql)
        self.assertEqual(customer_values, ("tamil", 11, 7))
        self.assertIn("organization_id=%s", call_sql)
        self.assertEqual(call_values, ("tamil", 42, 11, 7))
        connection.commit.assert_called_once_with()

    def test_unsupported_language_is_rejected_without_database_write(self):
        connection = MagicMock()
        with self.assertRaises(ValueError):
            call_log_service.update_selected_language(
                connection, 42, 7, 11, "hindi"
            )
        connection.cursor.assert_not_called()


class PlivoProviderTests(unittest.TestCase):
    def test_create_call_uses_all_lifecycle_urls(self):
        calls = Mock()
        calls.create.return_value = SimpleNamespace(
            request_uuid="request-1", api_id="api-1", message="call fired"
        )
        provider = PlivoProvider(
            auth_id="id", auth_token="token", from_number="+911234567890",
            client=SimpleNamespace(calls=calls),
        )
        result = provider.create_call(
            to="+919876543210",
            answer_url="https://example.test/answer",
            ring_url="https://example.test/ring",
            hangup_url="https://example.test/hangup",
            fallback_url="https://example.test/fallback",
            time_limit_seconds=900,
        )
        self.assertEqual(result.request_id, "request-1")
        calls.create.assert_called_once_with(
            from_="+911234567890",
            to_="+919876543210",
            answer_url="https://example.test/answer",
            answer_method="POST",
            ring_url="https://example.test/ring",
            ring_method="POST",
            hangup_url="https://example.test/hangup",
            hangup_method="POST",
            fallback_url="https://example.test/fallback",
            fallback_method="POST",
            time_limit=900,
        )

    def test_terminate_prefers_call_uuid_and_can_cancel_request(self):
        calls = Mock()
        provider = PlivoProvider(
            auth_id="id", auth_token="token", from_number="+911234567890",
            client=SimpleNamespace(calls=calls),
        )
        provider.terminate_call(call_id="call-1", request_id="request-1")
        calls.delete.assert_called_once_with("call-1")
        calls.cancel.assert_not_called()
        provider.terminate_call(call_id=None, request_id="request-2")
        calls.cancel.assert_called_once_with("request-2")

    def test_terminate_treats_already_ended_call_as_success(self):
        from plivo.exceptions import ResourceNotFoundError

        calls = Mock()
        calls.delete.side_effect = ResourceNotFoundError("not found")
        provider = PlivoProvider(
            auth_id="id", auth_token="token", from_number="+911234567890",
            client=SimpleNamespace(calls=calls),
        )
        # Must not raise: the caller already hung up (e.g. a missed hangup
        # webhook), so Plivo has nothing live left to terminate.
        provider.terminate_call(call_id="call-1", request_id=None)
        calls.delete.assert_called_once_with("call-1")

    def test_v3_signature_validation_accepts_and_rejects(self):
        utils_module = types.ModuleType("plivo.utils")
        validator = Mock(side_effect=[True, False])
        utils_module.validate_v3_signature = validator
        with patch.dict(sys.modules, {"plivo.utils": utils_module}):
            provider = PlivoProvider(
                auth_id="id", auth_token="token", from_number="+911234567890"
            )
            self.assertTrue(provider.validate_callback(
                method="POST", url="https://voice.test/callback",
                nonce="nonce", signature="valid", params={"CallUUID": "call-1"},
            ))
            self.assertFalse(provider.validate_callback(
                method="POST", url="https://voice.test/callback",
                nonce="nonce", signature="invalid", params={"CallUUID": "call-1"},
            ))


if __name__ == "__main__":
    unittest.main()
