"""Complete end-to-end testing of the Inbound Calling pipeline.

Tests verify:
1. DID resolution & normalization from dialed `To` header (phone_numbers table).
2. Unconfigured / inactive DID rejection with pre-rendered Play audio (HTTP 503).
3. Closed office detection with pre-rendered Play audio & Hangup (no carrier Speak).
4. Caller identification and customer deduplication (existing vs first-time caller).
5. Inbound call log creation with call_direction='inbound' and answered_at.
6. Plivo Answer redirect and Media Stream XML with HMAC token generation.
7. Tenant-scoped Plivo signature verification on incoming callbacks.
8. Realtime session greeting dispatch: natural receptionist greeting on inbound,
   preserving cold-call opening on outbound.
9. Pre-rendered WAV audio endpoints (/inbound-unconfigured.wav, /inbound-closed.wav).
10. Outbound pipeline non-interference assertion.
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api import plivo as plivo_api
from app.api import openai_realtime as realtime_api
from app.main import app
from app.services import (
    business_hours_service,
    call_log_service,
    conversation_policy_service,
    inbound_prompt_audio,
    phone_number_service,
)
from app.services.plivo_stream import validate_stream_token


class InboundPipelineComprehensiveTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.org_id = 42
        self.campaign_id = 7
        self.did = "918041234567"
        self.caller_phone = "+919876543210"
        self.caller_digits = "919876543210"

    def _make_inbound_request(self, to_number: str, from_number: str, call_uuid: str = "call-uuid-101") -> MagicMock:
        request = MagicMock()
        request.method = "POST"
        request.base_url = "https://voice.example.com/"
        request.url.query = ""
        self._form = {
            "To": to_number,
            "From": from_number,
            "CallUUID": call_uuid,
            "RequestUUID": "req-uuid-101",
        }
        return request

    # --- 1. DID Routing & Unconfigured Rejection ---

    async def test_unconfigured_did_returns_503_with_play_and_no_speak(self):
        db = MagicMock()
        request = self._make_inbound_request("919999999999", self.caller_phone)

        with patch.object(plivo_api, "_signed_form", new=AsyncMock(return_value=self._form)):
            with patch.object(phone_number_service, "get_active_route_for_number", return_value=None):
                with patch("app.api.plivo.call_log_service.create_call_log") as mock_create_log:
                    response = await plivo_api.inbound(request, db)

        self.assertEqual(503, response.status_code)
        self.assertIn(b"/api/plivo/inbound-unconfigured.wav</Play>", response.body)
        self.assertIn(b"<Hangup/>", response.body)
        self.assertNotIn(b"<Speak>", response.body)
        mock_create_log.assert_not_called()

    # --- 2. Business Hours Gate (Closed Office) ---

    async def test_closed_office_returns_200_with_play_and_hangup(self):
        db = MagicMock()
        request = self._make_inbound_request(self.did, self.caller_phone)
        route = {"organization_id": self.org_id, "campaign_id": self.campaign_id}

        with patch.object(plivo_api, "_signed_form", new=AsyncMock(return_value=self._form)):
            with patch.object(phone_number_service, "get_active_route_for_number", return_value=route):
                with patch.object(business_hours_service, "is_open_now", return_value={"is_open": False}):
                    with patch("app.api.plivo.call_log_service.create_call_log") as mock_create_log:
                        response = await plivo_api.inbound(request, db)

        self.assertEqual(200, response.status_code)
        self.assertIn(b"/api/plivo/inbound-closed.wav</Play>", response.body)
        self.assertIn(b"<Hangup/>", response.body)
        self.assertNotIn(b"<Speak>", response.body)
        mock_create_log.assert_not_called()

    # --- 3. First-Time Caller Customer Creation & Inbound Call Log ---

    async def test_open_office_new_caller_creates_customer_and_inbound_call_log(self):
        db = MagicMock()
        cursor = db.cursor.return_value
        cursor.fetchone.return_value = None  # no customer match
        cursor.lastrowid = 888  # new customer ID
        request = self._make_inbound_request(self.did, self.caller_phone, call_uuid="call-12345")
        route = {"organization_id": self.org_id, "campaign_id": self.campaign_id}

        with patch.object(plivo_api, "_signed_form", new=AsyncMock(return_value=self._form)):
            with patch.object(phone_number_service, "get_active_route_for_number", return_value=route):
                with patch.object(business_hours_service, "is_open_now", return_value={"is_open": True}):
                    with patch.object(call_log_service, "get_call_log_by_sid", return_value=None):
                        with patch.object(
                            call_log_service, "create_call_log",
                            return_value={"id": 777, "correlation_id": "in_call-12345"},
                        ) as mock_create_log:
                            response = await plivo_api.inbound(request, db)

        self.assertEqual(200, response.status_code)
        mock_create_log.assert_called_once()
        self.assertEqual(self.org_id, mock_create_log.call_args.args[1])
        self.assertEqual(888, mock_create_log.call_args.args[2])  # customer_id
        self.assertEqual(self.campaign_id, mock_create_log.call_args.args[3])

        # Verify call_direction='inbound' was set
        update_calls = [
            call for call in cursor.execute.call_args_list
            if "UPDATE call_logs SET call_direction='inbound'" in str(call)
        ]
        self.assertTrue(len(update_calls) > 0, "Expected call_direction='inbound' UPDATE on call_logs")

        # Verify Redirect to /api/plivo/answer with correct parameters
        self.assertIn(b"<Redirect method=\"POST\">", response.body)
        self.assertIn(b"customer_id=888", response.body)
        self.assertIn(b"campaign_id=7", response.body)
        self.assertIn(b"correlation_id=in_call-12345", response.body)

    # --- 4. Existing Customer Match ---

    async def test_open_office_existing_caller_reuses_customer_record(self):
        db = MagicMock()
        cursor = db.cursor.return_value
        cursor.fetchone.return_value = {"id": 333}  # existing customer match
        request = self._make_inbound_request(self.did, self.caller_phone, call_uuid="call-54321")
        route = {"organization_id": self.org_id, "campaign_id": self.campaign_id}

        with patch.object(plivo_api, "_signed_form", new=AsyncMock(return_value=self._form)):
            with patch.object(phone_number_service, "get_active_route_for_number", return_value=route):
                with patch.object(business_hours_service, "is_open_now", return_value={"is_open": True}):
                    with patch.object(call_log_service, "get_call_log_by_sid", return_value=None):
                        with patch.object(
                            call_log_service, "create_call_log",
                            return_value={"id": 999, "correlation_id": "in_call-54321"},
                        ) as mock_create_log:
                            response = await plivo_api.inbound(request, db)

        self.assertEqual(200, response.status_code)
        mock_create_log.assert_called_once()
        self.assertEqual(333, mock_create_log.call_args.args[2])  # customer_id re-used
        self.assertIn(b"customer_id=333", response.body)

    # --- 5. Answer Callback Generates Valid Media Stream XML & HMAC Token ---

    async def test_answer_callback_generates_stream_xml_with_valid_hmac_token(self):
        db = MagicMock()
        request = MagicMock()
        request.method = "POST"
        request.base_url = "https://voice.example.com/"
        request.url.query = ""

        answer_form = {
            "CallUUID": "call-12345",
            "From": self.caller_phone,
            "To": self.did,
        }

        with patch.dict(os.environ, {"PLIVO_STREAM_TOKEN_SECRET": "test-stream-secret"}):
            with patch.object(plivo_api, "_signed_form", new=AsyncMock(return_value=answer_form)):
                with patch.object(call_log_service, "update_call_log_status") as mock_update_status:
                    response = await plivo_api.answer(
                        request=request,
                        db=db,
                        customer_id=888,
                        campaign_id=7,
                        correlation_id="in_call-12345",
                    )

            self.assertEqual(200, response.status_code)
            self.assertIn(b"<Stream", response.body)
            self.assertIn(b"keepCallAlive=\"true\"", response.body)
            mock_update_status.assert_called_once_with(db, "call-12345", "in-progress")

            # Extract wss stream URL and validate the embedded HMAC stream token
            import html, re
            body_str = response.body.decode("utf-8")
            match = re.search(r"<Stream[^>]*>(.*?)</Stream>", body_str)
            self.assertIsNotNone(match)
            stream_url = html.unescape(match.group(1).strip())
            parsed_url = urlparse(stream_url)
            params = parse_qs(parsed_url.query)
            token = params.get("token", [""])[0]

            self.assertTrue(
                validate_stream_token(token, 888, 7, "in_call-12345"),
                "Expected generated stream token to be cryptographically valid",
            )

    # --- 6. Tenant-Scoped Signature Verification for Inbound Calls ---

    async def test_signed_form_resolves_tenant_from_dialed_to_when_correlation_absent(self):
        db = MagicMock()
        request = MagicMock()
        request.method = "POST"
        request.form = AsyncMock(return_value={"To": "+91 80 4123 4567", "From": "+919876543210"})
        request.query_params = {}
        request.headers = {
            "X-Plivo-Signature-V3": "mock-sig",
            "X-Plivo-Signature-V3-Nonce": "mock-nonce",
        }

        provider = MagicMock()
        provider.validate_callback.return_value = True

        with patch.dict(os.environ, {"PLIVO_VALIDATE_SIGNATURES": "true", "ENVIRONMENT": "production"}):
            with patch.object(
                phone_number_service, "get_active_route_for_number",
                return_value={"organization_id": 99, "campaign_id": 14},
            ):
                with patch("app.api.plivo.get_telephony_provider", return_value=provider) as get_provider:
                    with patch("app.api.plivo._callback_url", return_value="https://voice.example.com/api/plivo/inbound"):
                        form = await plivo_api._signed_form(request, db)

        self.assertEqual(form["To"], "+91 80 4123 4567")
        get_provider.assert_called_once_with(db, 99)
        provider.validate_callback.assert_called_once()

    async def test_signed_form_rejects_tampered_signature_with_403(self):
        db = MagicMock()
        request = MagicMock()
        request.method = "POST"
        request.form = AsyncMock(return_value={"To": "+91 80 4123 4567", "From": "+919876543210"})
        request.query_params = {}
        request.headers = {
            "X-Plivo-Signature-V3": "bad-sig",
            "X-Plivo-Signature-V3-Nonce": "bad-nonce",
        }

        provider = MagicMock()
        provider.validate_callback.return_value = False

        with patch.dict(os.environ, {"PLIVO_VALIDATE_SIGNATURES": "true", "ENVIRONMENT": "production"}):
            with patch.object(
                phone_number_service, "get_active_route_for_number",
                return_value={"organization_id": 99, "campaign_id": 14},
            ):
                with patch("app.api.plivo.get_telephony_provider", return_value=provider):
                    with patch("app.api.plivo._callback_url", return_value="https://voice.example.com/api/plivo/inbound"):
                        with self.assertRaises(HTTPException) as raised:
                            await plivo_api._signed_form(request, db)

        self.assertEqual(403, raised.exception.status_code)
        self.assertEqual("Invalid Plivo V3 signature", raised.exception.detail)


class InboundAudioEndpointsAndGreetingsTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    # --- 7. Pre-rendered Audio Endpoints HTTP 200 ---

    def test_inbound_audio_endpoints_return_200_and_wav_content_type(self):
        with patch("app.services.inbound_prompt_audio.ensure_prompt_audio") as mock_ensure:
            mock_path = MagicMock()
            mock_path.read_bytes.return_value = b"RIFF\x24\x00\x00\x00WAVEfmt "
            mock_ensure.return_value = mock_path

            resp_unconfigured = self.client.get("/api/plivo/inbound-unconfigured.wav")
            self.assertEqual(200, resp_unconfigured.status_code)
            self.assertEqual("audio/wav", resp_unconfigured.headers["content-type"])
            self.assertEqual(b"RIFF\x24\x00\x00\x00WAVEfmt ", resp_unconfigured.content)

            resp_closed = self.client.get("/api/plivo/inbound-closed.wav")
            self.assertEqual(200, resp_closed.status_code)
            self.assertEqual("audio/wav", resp_closed.headers["content-type"])
            self.assertEqual(b"RIFF\x24\x00\x00\x00WAVEfmt ", resp_closed.content)

    # --- 8. Receptionist Greeting Selection by Call Direction ---

    def test_inbound_vs_outbound_greeting_isolation(self):
        customer = {"name": "Priya"}

        # Inbound English
        inbound_en = realtime_api._greeting_instruction(
            customer, "english", organization_name="DigiDara Tech", call_direction="inbound",
        )
        self.assertIn("Thank you for calling DigiDara Tech. I am the AI voice assistant. How can I help you today?", inbound_en)
        self.assertNotIn("Is this a good time to speak?", inbound_en)

        # Inbound Tamil
        inbound_ta = realtime_api._greeting_instruction(
            customer, "tamil", organization_name="DigiDara Tech", call_direction="inbound",
        )
        self.assertIn("வணக்கம், DigiDara Tech-ஐ தொடர்பு கொண்டதற்கு நன்றி", inbound_ta)
        self.assertIn("உங்களுக்கு நான் எப்படி உதவ முடியும்?", inbound_ta)
        self.assertNotIn("இப்ப பேச வசதியா?", inbound_ta)

        # Outbound English (must remain untouched cold-call opening)
        outbound_en = realtime_api._greeting_instruction(
            customer, "english", organization_name="DigiDara Tech", call_direction="outbound",
        )
        self.assertIn("Is this a good time to speak?", outbound_en)
        self.assertNotIn("How can I help you today?", outbound_en)

        # Outbound Tamil (must remain untouched cold-call opening)
        outbound_ta = realtime_api._greeting_instruction(
            customer, "tamil", organization_name="DigiDara Tech", call_direction="outbound",
        )
        self.assertIn("இப்ப பேச வசதியா?", outbound_ta)
        self.assertNotIn("எப்படி உதவ முடியும்?", outbound_ta)


if __name__ == "__main__":
    unittest.main()
