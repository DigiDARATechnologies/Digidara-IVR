import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import pymysql
from fastapi import HTTPException

from app.api import phone_numbers as phone_numbers_api
from app.api import plivo as plivo_api
from app.schemas.phone_number import PhoneNumberCreate, PhoneNumberUpdate
from app.services import phone_number_service


class NormalizeNumberTests(unittest.TestCase):
    def test_strips_everything_but_digits(self):
        self.assertEqual(phone_number_service.normalize_number("+91 80-4123-4567"), "918041234567")
        self.assertEqual(phone_number_service.normalize_number("918041234567"), "918041234567")
        self.assertEqual(phone_number_service.normalize_number(""), "")

    def test_schema_normalizes_on_input(self):
        payload = PhoneNumberCreate(plivo_number="+91 80 4123 4567", campaign_id=3)
        self.assertEqual(payload.plivo_number, "918041234567")

    def test_schema_rejects_number_with_no_digits(self):
        with self.assertRaises(ValueError):
            PhoneNumberCreate(plivo_number="abc", campaign_id=3)


class PhoneNumberServiceTests(unittest.TestCase):
    def test_get_active_route_normalizes_and_filters_inactive(self):
        db = MagicMock()
        db.cursor.return_value.fetchone.return_value = {
            "id": 1, "organization_id": 42, "campaign_id": 7,
            "plivo_number": "918041234567", "label": None,
            "is_active": True, "created_at": "2026-09-15",
        }
        route = phone_number_service.get_active_route_for_number(db, "+91 80 4123 4567")
        executed_sql, params = db.cursor.return_value.execute.call_args.args
        self.assertIn("is_active=TRUE", executed_sql)
        self.assertEqual(("918041234567",), params)
        self.assertEqual(42, route["organization_id"])
        self.assertEqual(7, route["campaign_id"])

    def test_get_active_route_returns_none_for_blank_number(self):
        db = MagicMock()
        self.assertIsNone(phone_number_service.get_active_route_for_number(db, ""))
        db.cursor.return_value.execute.assert_not_called()

    def test_get_active_route_returns_none_when_unregistered(self):
        db = MagicMock()
        db.cursor.return_value.fetchone.return_value = None
        self.assertIsNone(phone_number_service.get_active_route_for_number(db, "918041234567"))

    def test_create_inserts_scoped_to_organization_and_commits(self):
        db = MagicMock()
        db.cursor.return_value.lastrowid = 9
        with patch.object(phone_number_service, "get_by_id", return_value={"id": 9}) as get_by_id:
            result = phone_number_service.create(
                db, 42, PhoneNumberCreate(plivo_number="918041234567", campaign_id=7, label="Front desk"),
            )
        insert_sql, insert_params = db.cursor.return_value.execute.call_args.args
        self.assertIn("INSERT INTO phone_numbers", insert_sql)
        self.assertEqual((42, 7, "918041234567", "Front desk", True), insert_params)
        db.commit.assert_called_once()
        get_by_id.assert_called_once_with(db, 9, 42)
        self.assertEqual({"id": 9}, result)

    def test_update_only_touches_provided_fields(self):
        db = MagicMock()
        with patch.object(
            phone_number_service, "get_by_id", return_value={"id": 1, "organization_id": 42},
        ):
            phone_number_service.update(db, 1, 42, PhoneNumberUpdate(is_active=False))
        update_sql, update_params = db.cursor.return_value.execute.call_args.args
        self.assertIn("SET is_active = %s", update_sql)
        self.assertEqual((False, 1, 42), update_params)

    def test_update_returns_none_when_not_found(self):
        db = MagicMock()
        with patch.object(phone_number_service, "get_by_id", return_value=None):
            result = phone_number_service.update(db, 1, 42, PhoneNumberUpdate(label="x"))
        self.assertIsNone(result)

    def test_delete_scopes_to_organization(self):
        db = MagicMock()
        with patch.object(phone_number_service, "get_by_id", return_value={"id": 1}):
            self.assertTrue(phone_number_service.delete(db, 1, 42))
        delete_sql, delete_params = db.cursor.return_value.execute.call_args.args
        self.assertIn("DELETE FROM phone_numbers", delete_sql)
        self.assertEqual((1, 42), delete_params)

    def test_delete_returns_false_when_not_found(self):
        db = MagicMock()
        with patch.object(phone_number_service, "get_by_id", return_value=None):
            self.assertFalse(phone_number_service.delete(db, 1, 42))


class PhoneNumberApiTests(unittest.TestCase):
    def test_create_rejects_campaign_from_another_organization(self):
        db = MagicMock()
        with patch("app.api.phone_numbers.campaign_service.get_campaign_by_id", return_value=None):
            with self.assertRaises(HTTPException) as raised:
                phone_numbers_api.create_phone_number(
                    PhoneNumberCreate(plivo_number="918041234567", campaign_id=999),
                    admin={"organization_id": 42},
                    db=db,
                )
        self.assertEqual(400, raised.exception.status_code)

    def test_create_rejects_duplicate_number(self):
        db = MagicMock()
        with patch("app.api.phone_numbers.campaign_service.get_campaign_by_id", return_value={"id": 7}):
            with patch(
                "app.api.phone_numbers.phone_number_service.create",
                side_effect=pymysql.IntegrityError(1062, "Duplicate entry"),
            ):
                with self.assertRaises(HTTPException) as raised:
                    phone_numbers_api.create_phone_number(
                        PhoneNumberCreate(plivo_number="918041234567", campaign_id=7),
                        admin={"organization_id": 42},
                        db=db,
                    )
        self.assertEqual(400, raised.exception.status_code)

    def test_update_404_when_not_found(self):
        db = MagicMock()
        with patch("app.api.phone_numbers.phone_number_service.update", return_value=None):
            with self.assertRaises(HTTPException) as raised:
                phone_numbers_api.update_phone_number(
                    1, PhoneNumberUpdate(label="x"), admin={"organization_id": 42}, db=db,
                )
        self.assertEqual(404, raised.exception.status_code)

    def test_delete_404_when_not_found(self):
        db = MagicMock()
        with patch("app.api.phone_numbers.phone_number_service.delete", return_value=False):
            with self.assertRaises(HTTPException) as raised:
                phone_numbers_api.delete_phone_number(1, admin={"organization_id": 42}, db=db)
        self.assertEqual(404, raised.exception.status_code)


class InboundDidRoutingTests(unittest.IsolatedAsyncioTestCase):
    """/api/plivo/inbound must route by the dialed DID (phone_numbers table),
    not the old single global PLIVO_INBOUND_CAMPAIGN_ID env var."""

    def _request(self, form: dict) -> MagicMock:
        request = MagicMock()
        request.method = "POST"
        request.base_url = "https://voice.example.com/"
        request.url.query = ""
        self._form = form
        return request

    async def test_unregistered_number_returns_503_without_creating_a_call_log(self):
        db = MagicMock()
        request = self._request({"To": "919999999999", "From": "911234567890"})
        with patch.object(plivo_api, "_signed_form", new=AsyncMock(return_value=self._form)):
            with patch.object(phone_number_service, "get_active_route_for_number", return_value=None):
                with patch("app.api.plivo.call_log_service.create_call_log") as create_call_log:
                    response = await plivo_api.inbound(request, db)
        self.assertEqual(503, response.status_code)
        self.assertIn(b"inbound-unconfigured.wav", response.body)
        self.assertNotIn(b"<Speak>", response.body)
        create_call_log.assert_not_called()

    async def test_closed_office_returns_pre_rendered_play_without_carrier_speak(self):
        db = MagicMock()
        request = self._request({"To": "918041234567", "From": "911234567890"})
        route = {"organization_id": 42, "campaign_id": 7}
        with patch.object(plivo_api, "_signed_form", new=AsyncMock(return_value=self._form)):
            with patch.object(phone_number_service, "get_active_route_for_number", return_value=route):
                with patch("app.api.plivo.business_hours_service.is_open_now", return_value={"is_open": False}):
                    with patch("app.api.plivo.call_log_service.create_call_log") as create_call_log:
                        response = await plivo_api.inbound(request, db)
        self.assertEqual(200, response.status_code)
        self.assertIn(b"inbound-closed.wav", response.body)
        self.assertIn(b"<Hangup/>", response.body)
        self.assertNotIn(b"<Speak>", response.body)
        create_call_log.assert_not_called()

    async def test_registered_number_routes_to_its_own_organization_and_campaign(self):
        db = MagicMock()
        db.cursor.return_value.fetchone.return_value = None  # no existing customer match
        db.cursor.return_value.lastrowid = 501
        request = self._request({
            "To": "918041234567", "From": "911234567890", "CallUUID": "call-uuid-1",
        })
        route = {"organization_id": 42, "campaign_id": 7}
        with patch.object(plivo_api, "_signed_form", new=AsyncMock(return_value=self._form)):
            with patch.object(phone_number_service, "get_active_route_for_number", return_value=route) as lookup:
                with patch("app.api.plivo.business_hours_service.is_open_now", return_value={"is_open": True}):
                    with patch(
                        "app.api.plivo.call_log_service.get_call_log_by_sid", return_value=None,
                    ):
                        with patch(
                            "app.api.plivo.call_log_service.create_call_log",
                            return_value={"id": 1001},
                        ) as create_call_log:
                            response = await plivo_api.inbound(request, db)

        lookup.assert_called_once_with(db, "918041234567")
        self.assertEqual(200, response.status_code)
        create_call_log.assert_called_once()
        self.assertEqual(42, create_call_log.call_args.args[1])  # organization_id
        self.assertEqual(7, create_call_log.call_args.args[3])  # campaign_id
        self.assertIn(b"campaign_id=7", response.body)

    async def test_signed_form_resolves_organization_from_dialed_to_number(self):
        db = MagicMock()
        request = MagicMock()
        request.method = "POST"
        request.form = AsyncMock(return_value={"To": "+918041234567", "From": "+919876543210"})
        request.query_params = {}
        request.headers = {
            "X-Plivo-Signature-V3": "valid-sig",
            "X-Plivo-Signature-V3-Nonce": "nonce-1",
        }
        provider = MagicMock()
        provider.validate_callback.return_value = True
        with patch.dict("os.environ", {"PLIVO_VALIDATE_SIGNATURES": "true", "ENVIRONMENT": "production"}):
            with patch.object(
                phone_number_service, "get_active_route_for_number",
                return_value={"organization_id": 88, "campaign_id": 12},
            ):
                with patch("app.api.plivo.get_telephony_provider", return_value=provider) as get_provider:
                    with patch("app.api.plivo._callback_url", return_value="https://voice.example.com/api/plivo/inbound"):
                        form = await plivo_api._signed_form(request, db)

        self.assertEqual(form["To"], "+918041234567")
        get_provider.assert_called_once_with(db, 88)
        provider.validate_callback.assert_called_once()

    async def test_inbound_audio_endpoints(self):
        with patch("app.services.inbound_prompt_audio.ensure_prompt_audio") as mock_ensure:
            mock_file = MagicMock()
            mock_file.read_bytes.return_value = b"RIFFWAVE"
            mock_ensure.return_value = mock_file

            unconfigured_resp = await plivo_api.inbound_unconfigured_audio()
            self.assertEqual(200, unconfigured_resp.status_code)
            self.assertEqual(b"RIFFWAVE", unconfigured_resp.body)

            closed_resp = await plivo_api.inbound_closed_audio()
            self.assertEqual(200, closed_resp.status_code)
            self.assertEqual(b"RIFFWAVE", closed_resp.body)


class InboundGreetingInstructionTests(unittest.TestCase):
    def test_inbound_greeting_tamil_and_english(self):
        from app.services.conversation_policy_service import build_inbound_greeting_instruction

        tamil = build_inbound_greeting_instruction("tamil", organization_name="Acme Corp")
        self.assertIn("Acme Corp", tamil)
        self.assertIn("வணக்கம்", tamil)
        self.assertIn("எப்படி உதவ முடியும்", tamil)
        self.assertNotIn("இப்ப பேச வசதியா", tamil)

        english = build_inbound_greeting_instruction("english", organization_name="Acme Corp")
        self.assertIn("Thank you for calling Acme Corp", english)
        self.assertIn("How can I help you today?", english)
        self.assertNotIn("Is this a good time to speak?", english)

    def test_realtime_greeting_instruction_dispatches_by_call_direction(self):
        from app.api.openai_realtime import _greeting_instruction

        operator = {"name": "Test Customer"}
        inbound_greeting = _greeting_instruction(operator, "english", "Acme Corp", call_direction="inbound")
        self.assertIn("How can I help you today?", inbound_greeting)

        outbound_greeting = _greeting_instruction(operator, "english", "Acme Corp", call_direction="outbound")
        self.assertIn("Is this a good time to speak?", outbound_greeting)


if __name__ == "__main__":
    unittest.main()
