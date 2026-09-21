import os
from pathlib import Path
import unittest
from unittest.mock import patch

from app.services.realtime_turns import (
    bounded_float_env,
    bounded_int_env,
    parse_playback_mark,
    playback_mark_name,
)
from app.api.openai_realtime import (
    _end_call_tool_definition,
    _greeting_instruction,
    _instructions,
    _route_to_human_tool_definition,
    _router_instructions,
    _transfer_to_human_tool_definition,
    build_turn_detection_config,
    resolve_vad_eagerness,
)


class IvrRouterInstructionsTests(unittest.TestCase):
    def test_router_instructions_use_configured_prompt_and_labels_not_course(self):
        menu = {
            "prompt": "What do you need — Business, Support, or Education?",
            "options": [
                {"label": "Business"}, {"label": "Support"}, {"label": "Education"},
            ],
        }
        text = _router_instructions("english", menu, "DigiDara Technologies")
        self.assertIn("DigiDara Technologies", text)
        self.assertIn("Business, Support, Education", text)
        self.assertIn("route_to_human", text)
        self.assertNotIn("course", text.lower())
        self.assertNotIn("enquiry", text.lower())
        self.assertIn("can't answer that", text)

    def test_router_instructions_fall_back_to_a_generated_question_when_no_prompt_set(self):
        menu = {"prompt": "", "options": [{"label": "Sales"}, {"label": "Support"}]}
        text = _router_instructions("english", menu, "Acme")
        self.assertIn("Sales, Support", text)

    def test_tamil_router_instructions_avoid_course_wording_too(self):
        menu = {"prompt": "", "options": [{"label": "Business"}, {"label": "Support"}]}
        text = _router_instructions("tamil", menu, "DigiDara")
        self.assertIn("route_to_human", text)
        self.assertNotIn("course", text.lower())

    def test_route_to_human_tool_lists_exact_configured_labels(self):
        tool = _route_to_human_tool_definition(["Business", "Support", "Education"])
        self.assertEqual("route_to_human", tool["name"])
        self.assertEqual(
            ["Business", "Support", "Education"],
            tool["parameters"]["properties"]["department"]["enum"],
        )
        self.assertEqual(["department"], tool["parameters"]["required"])

    def test_end_call_tool_definition_matches_the_original_shape(self):
        tool = _end_call_tool_definition()
        self.assertEqual("end_call", tool["name"])
        self.assertEqual(
            {"customer_goodbye", "customer_not_interested", "customer_do_not_call", "other"},
            set(tool["parameters"]["properties"]["reason"]["enum"]),
        )

    def test_transfer_to_human_tool_takes_no_arguments(self):
        tool = _transfer_to_human_tool_definition()
        self.assertEqual("transfer_to_human", tool["name"])
        self.assertEqual({}, tool["parameters"]["properties"])
        self.assertEqual([], tool["parameters"]["required"])


class PlaybackMarkTests(unittest.TestCase):
    def test_mark_round_trip_keeps_item_and_position(self):
        name = playback_mark_name("item_abc123", 1480)
        self.assertEqual(parse_playback_mark(name), ("item_abc123", 1480))

    def test_foreign_and_malformed_marks_are_ignored(self):
        self.assertEqual(parse_playback_mark("other|item|120"), (None, None))
        self.assertEqual(parse_playback_mark("rt|item|bad"), (None, None))
        self.assertEqual(parse_playback_mark(""), (None, None))

    def test_negative_position_is_clamped(self):
        self.assertEqual(parse_playback_mark("rt|item_1|-5"), ("item_1", 0))


class RuntimeConfigurationTests(unittest.TestCase):
    def test_bad_integer_setting_uses_default(self):
        with patch.dict(os.environ, {"TEST_MARK_INTERVAL": "not-a-number"}):
            self.assertEqual(bounded_int_env("TEST_MARK_INTERVAL", 240, 100, 1000), 240)

    def test_integer_setting_is_bounded(self):
        with patch.dict(os.environ, {"TEST_MARK_INTERVAL": "10"}):
            self.assertEqual(bounded_int_env("TEST_MARK_INTERVAL", 240, 100, 1000), 100)
        with patch.dict(os.environ, {"TEST_MARK_INTERVAL": "5000"}):
            self.assertEqual(bounded_int_env("TEST_MARK_INTERVAL", 240, 100, 1000), 1000)

    def test_bad_float_setting_uses_default(self):
        with patch.dict(os.environ, {"TEST_THRESHOLD": "not-a-number"}):
            self.assertEqual(bounded_float_env("TEST_THRESHOLD", 0.6, 0.3, 0.9), 0.6)

    def test_float_setting_is_bounded(self):
        with patch.dict(os.environ, {"TEST_THRESHOLD": "0.1"}):
            self.assertEqual(bounded_float_env("TEST_THRESHOLD", 0.6, 0.3, 0.9), 0.3)
        with patch.dict(os.environ, {"TEST_THRESHOLD": "0.99"}):
            self.assertEqual(bounded_float_env("TEST_THRESHOLD", 0.6, 0.3, 0.9), 0.9)
        with patch.dict(os.environ, {"TEST_THRESHOLD": "0.75"}):
            self.assertEqual(bounded_float_env("TEST_THRESHOLD", 0.6, 0.3, 0.9), 0.75)

    def test_english_uses_bounded_server_vad_and_tamil_keeps_semantic_gate(self):
        with patch.dict(os.environ, {}, clear=True):
            english = build_turn_detection_config("english")
            tamil = build_turn_detection_config("tamil")
        self.assertEqual(english, {
            "type": "server_vad",
            "threshold": 0.6,
            "prefix_padding_ms": 300,
            "silence_duration_ms": 650,
            "create_response": True,
            "interrupt_response": True,
        })
        self.assertEqual(tamil["type"], "semantic_vad")
        self.assertEqual(tamil["eagerness"], "high")
        self.assertFalse(tamil["create_response"])
        self.assertFalse(tamil["interrupt_response"])

    def test_english_server_vad_threshold_is_bounded(self):
        with patch.dict(os.environ, {"OPENAI_SERVER_VAD_THRESHOLD_ENGLISH": "0.1"}, clear=True):
            self.assertEqual(build_turn_detection_config("english")["threshold"], 0.3)
        with patch.dict(os.environ, {"OPENAI_SERVER_VAD_THRESHOLD_ENGLISH": "0.99"}, clear=True):
            self.assertEqual(build_turn_detection_config("english")["threshold"], 0.9)
        with patch.dict(os.environ, {"OPENAI_SERVER_VAD_THRESHOLD_ENGLISH": "not-a-number"}, clear=True):
            self.assertEqual(build_turn_detection_config("english")["threshold"], 0.6)

    def test_invalid_vad_setting_falls_back_to_language_default(self):
        with patch.dict(os.environ, {
            "OPENAI_VAD_EAGERNESS_ENGLISH": "too-fast",
            "OPENAI_VAD_EAGERNESS_TAMIL": "too-slow",
        }, clear=True):
            self.assertEqual(resolve_vad_eagerness("english"), "medium")
            self.assertEqual(resolve_vad_eagerness("tamil"), "high")

    def test_english_server_vad_silence_is_bounded(self):
        with patch.dict(os.environ, {
            "OPENAI_SERVER_VAD_SILENCE_MS_ENGLISH": "100",
        }, clear=True):
            self.assertEqual(
                build_turn_detection_config("english")["silence_duration_ms"], 400
            )
        with patch.dict(os.environ, {
            "OPENAI_SERVER_VAD_SILENCE_MS_ENGLISH": "5000",
        }, clear=True):
            self.assertEqual(
                build_turn_detection_config("english")["silence_duration_ms"], 1500
            )


class LanguageFlowTests(unittest.TestCase):
    def test_route_preserves_english_and_validates_tamil_latest_turns(self):
        source = Path("app/api/openai_realtime.py").read_text(encoding="utf-8")
        # The live receptionist path must not depend on the Facility module —
        # it uses the generic, tenant-agnostic conversation_policy_service
        # prompt builders instead.
        self.assertNotIn("app.facility", source)
        self.assertNotIn("FacilityRagService", source)
        self.assertNotIn("should_retrieve_facility_knowledge", source)
        self.assertIn("build_initial_session_instructions", source)
        self.assertIn("build_existing_english_session_instructions", source)
        self.assertIn("build_response_instruction", source)
        self.assertIn("build_greeting_instruction", source)
        self.assertNotIn("search_knowledge(", source)
        self.assertIn('"create_response": automatic_response', source)
        self.assertIn('"interrupt_response": automatic_response', source)
        self.assertIn('"type": "server_vad"', source)
        self.assertIn('"type": "semantic_vad"', source)
        self.assertIn('"openai_server_vad_english_v1"', source)
        self.assertIn('if language == "tamil":', source)
        self.assertIn("process_validated_turn(input_item_id)", source)
        self.assertIn("latest_customer_turn_id", source)
        self.assertIn("response_lock", source)
        self.assertIn("conversation.item.delete", source)
        self.assertIn("duplicate Plivo stream rejected", source)
        self.assertIn('"/ws/plivo/media"', source)
        self.assertIn("clear_audio(stream_sid)", source)
        self.assertIn("confirm_barge_in", source)
        self.assertIn('f"{env_prefix}_BARGE_IN_CONFIRM_MS"', source)
        self.assertIn("OPENAI_TRANSCRIPTION_MODEL_TAMIL", source)
        self.assertIn('"transcription": transcription_config', source)
        self.assertIn("estimate_openai_cost_usd(", source)
        self.assertIn("CONVERSATION_POLICY_PROFILE", source)

    def test_organization_name_is_resolved_and_threaded_to_the_greeting(self):
        source = Path("app/api/openai_realtime.py").read_text(encoding="utf-8")
        self.assertIn("SELECT name FROM organizations WHERE id=%s", source)
        self.assertIn("_instructions(language, operator, campaign, memory, organization_name)", source)
        self.assertIn("_greeting_instruction(customer, language, organization_name", source)


class OrganizationNameGreetingTests(unittest.TestCase):
    """The live call path's own wrapper functions around
    conversation_policy_service — confirms organization_name actually
    reaches the generated instructions, not just that it's threaded
    through call sites textually (covered above)."""

    def setUp(self):
        self.customer = {"name": "Kumar", "investigated_course": "AI and ML"}

    def test_instructions_default_to_digidara_for_unscoped_callers(self):
        text = _instructions("english", self.customer, None, None)
        self.assertIn("DigiDara Technologies", text)
        self.assertIn("AI and ML", text)

    def test_instructions_use_the_given_organization_name(self):
        text = _instructions(
            "english", self.customer, None, None, organization_name="Acme Corp",
        )
        self.assertIn("Acme Corp", text)
        self.assertNotIn("DigiDara", text)

    def test_tamil_instructions_use_the_given_organization_name(self):
        text = _instructions(
            "tamil", self.customer, None, None, organization_name="Acme Corp",
        )
        self.assertIn("Acme Corp", text)
        self.assertNotIn("DigiDara", text)

    def test_english_greeting_uses_the_given_organization_name(self):
        greeting = _greeting_instruction(self.customer, "english", "Acme Corp")
        self.assertIn("Acme Corp", greeting)
        self.assertNotIn("DigiDara", greeting)

    def test_tamil_greeting_uses_the_given_organization_name(self):
        greeting = _greeting_instruction(self.customer, "tamil", "Acme Corp")
        self.assertIn("Acme Corp", greeting)
        self.assertNotIn("DigiDara", greeting)


if __name__ == "__main__":
    unittest.main()
