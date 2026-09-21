import os
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.conversation_policy_service import (
    build_english_language_policy,
    build_existing_english_session_instructions,
    build_greeting_instruction,
    build_initial_session_instructions,
    build_response_instruction,
    build_shared_conversation_policy,
    build_tamil_language_policy,
    classify_intent,
    count_response_sentences,
    count_response_words,
    initial_prompt_metrics,
    is_callback_intent,
    is_do_not_call_intent,
    is_end_call_intent,
    is_not_interested_intent,
    is_short_acknowledgement,
    is_stop_intent,
    should_retrieve_knowledge,
)
from app.services.tamil_conversation_service import resolve_realtime_voice
from app.utils.token_estimator import estimate_prompt_tokens


class SharedPolicyTests(unittest.TestCase):
    def setUp(self):
        self.customer = {
            "name": "Kumar",
            "language": "tamil",
            "investigated_course": "AI and ML",
        }
        self.campaign = {
            "objective": "Follow up on the enquiry.",
            "ai_prompt": "Ask the joining goal and agree a verified next step.",
        }

    def test_policy_token_budgets(self):
        self.assertLessEqual(estimate_prompt_tokens(build_shared_conversation_policy()), 500)
        self.assertLessEqual(estimate_prompt_tokens(build_tamil_language_policy()), 300)
        self.assertLessEqual(estimate_prompt_tokens(build_english_language_policy()), 220)
        self.assertLessEqual(
            initial_prompt_metrics("tamil", self.customer, self.campaign)["total_estimated_tokens"],
            1200,
        )
        self.assertLessEqual(
            initial_prompt_metrics("english", self.customer, self.campaign)["total_estimated_tokens"],
            1200,
        )

    def test_shared_policy_declines_off_topic_questions_instead_of_answering(self):
        policy = build_shared_conversation_policy("Acme Corp")
        self.assertIn("Only answer questions about Acme Corp's business", policy)
        self.assertIn("can't help with that", policy)

    def test_established_english_flow_also_declines_off_topic_questions(self):
        prompt = build_existing_english_session_instructions(
            self.customer, self.campaign, organization_name="Acme Corp",
        )
        self.assertIn("Only answer questions about Acme Corp's business", prompt)

    def test_both_initial_prompts_exclude_full_knowledge(self):
        for language in ("english", "tamil"):
            prompt = build_initial_session_instructions(
                language, self.customer, self.campaign, "Asked about timing"
            )
            self.assertNotIn("FACTUAL REFERENCE", prompt)
            self.assertIn("Prefer one short sentence", prompt)

    def test_established_english_flow_keeps_sales_playbook_and_knowledge(self):
        prompt = build_existing_english_session_instructions(
            self.customer,
            self.campaign,
            "Asked about timing",
            "Verified English fact",
        )
        self.assertIn("SALES EXECUTIVE ROLE", prompt)
        self.assertIn("COURSE ROUTE", prompt)
        self.assertIn("Verified English fact", prompt)
        self.assertIn("Asked about timing", prompt)

    def test_english_is_clear_slow_and_short_by_default(self):
        language_policy = build_english_language_policy()
        full_prompt = build_existing_english_session_instructions(
            self.customer,
            self.campaign,
            "Asked about timing",
            "Verified English fact",
        )
        for prompt in (language_policy, full_prompt):
            self.assertIn("slowly and clearly", prompt)
            self.assertIn("easy-to-understand Indian English", prompt)
            self.assertIn("8–20 spoken words", prompt)
            self.assertIn("28 words", prompt)
        self.assertIn("THIS OVERRIDES LONGER EXAMPLES", full_prompt)
        self.assertIn("Do not volunteer a pitch", full_prompt)

    def test_unclear_speech_clarifies_instead_of_ending_call(self):
        for prompt in (
            build_shared_conversation_policy(),
            build_existing_english_session_instructions(
                self.customer,
                self.campaign,
                "Asked about timing",
                "Verified English fact",
            ),
        ):
            self.assertIn("unintelligible speech", prompt)
            self.assertIn("never evidence", prompt)
            self.assertIn("keep the call open", prompt)

    def test_english_switches_only_on_explicit_customer_request(self):
        for prompt in (
            build_english_language_policy(),
            build_existing_english_session_instructions(
                self.customer,
                self.campaign,
                "Asked about timing",
                "Verified English fact",
            ),
        ):
            self.assertIn("Stay in English", prompt)
            self.assertIn("explicitly asks to speak Tamil", prompt)

    def test_response_instruction_is_query_first_and_short(self):
        english = build_response_instruction("english", "What is the fee?")
        tamil = build_response_instruction("tamil", "Fees எவ்வளவு?")
        self.assertIn("latest question", english)
        self.assertIn("second sentence only if necessary", english)
        self.assertIn("latest question", tamil)
        self.assertIn("ஒரு short sentence", tamil)

    def test_response_instruction_forbids_re_greeting_after_interruption(self):
        # Regression test for a real call (call-log 50) where the mini model
        # re-introduced itself repeatedly after being interrupted/regenerated
        # instead of following the fixed "are you still there" reprompt.
        english = build_response_instruction("english", "What is the fee?")
        self.assertIn("never reintroduce yourself", english)
        self.assertIn("interrupted", english)
        tamil = build_response_instruction("tamil", "Fees evlo")
        self.assertIn("greeting", tamil)

    def test_shared_and_established_english_prompts_forbid_re_greeting(self):
        shared = build_shared_conversation_policy()
        self.assertIn("re-greet", shared)
        established = build_existing_english_session_instructions(self.customer, self.campaign)
        self.assertIn("never reintroduce yourself", established)

    def test_greetings_disclose_ai_and_never_include_knowledge(self):
        for language in ("english", "tamil"):
            variants = {
                build_greeting_instruction(language, self.customer, seed)
                for seed in range(3)
            }
            self.assertEqual(len(variants), 3)
            for greeting in variants:
                self.assertIn("AI voice assistant", greeting)
                self.assertNotIn("FACTUAL REFERENCE", greeting)

    def test_response_metrics_count_words_and_sentences(self):
        self.assertEqual(count_response_words("Yes, evening batches are available."), 5)
        self.assertEqual(count_response_sentences("Yes. Shall I confirm the timing?"), 2)


class IntentPlannerTests(unittest.TestCase):
    def test_stop_phrases(self):
        for text in (
            "Stop", "Wait, let me speak", "Enough", "stop pannunga",
            "போதும்", "நிறுத்துங்க, நான் பேசுறேன்",
        ):
            self.assertTrue(is_stop_intent(text), text)
            self.assertEqual(classify_intent(text, "tamil"), "stop")
            self.assertFalse(should_retrieve_knowledge(text, "tamil"))

    def test_callback_phrases(self):
        for text in (
            "I am busy, call me later", "Call tomorrow",
            "இப்ப busy, later call பண்ணுங்க", "நாளைக்கு call பண்ணுங்க",
        ):
            self.assertTrue(is_callback_intent(text), text)
            self.assertEqual(classify_intent(text, "tamil"), "callback")
            self.assertFalse(should_retrieve_knowledge(text, "tamil"))
        self.assertEqual(classify_intent("busy"), "callback")

    def test_end_and_do_not_call_phrases(self):
        self.assertTrue(is_end_call_intent("Hang up", "english"))
        self.assertTrue(is_end_call_intent("Call cut பண்ணுங்க", "tamil"))
        self.assertTrue(is_end_call_intent("Not interested", "english"))
        self.assertTrue(is_do_not_call_intent("Do not call again"))
        self.assertTrue(is_do_not_call_intent("என் number remove பண்ணுங்க"))
        self.assertTrue(is_not_interested_intent("வேண்டாம்"))
        self.assertEqual(classify_intent("Not interested"), "not_interested")
        self.assertFalse(
            is_end_call_intent("Course வேண்டாம், internship சொல்லுங்க", "tamil")
        )

    def test_factual_queries_retrieve_in_both_languages(self):
        for language, text in (
            ("english", "What is the fee?"),
            ("english", "Do you have an evening batch?"),
            ("english", "Is placement guaranteed?"),
            ("tamil", "Fees எவ்வளவு?"),
            ("tamil", "Evening batch இருக்கா?"),
            ("tamil", "Placement guarantee இருக்கா?"),
        ):
            self.assertTrue(should_retrieve_knowledge(text, language), text)

    def test_language_switches_skip_retrieval(self):
        for text in ("Speak in Tamil", "Englishல பேசுங்க", "Tamil la pesu"):
            self.assertEqual(classify_intent(text, "english"), "language_switch")
            self.assertFalse(should_retrieve_knowledge(text, "english"))

    def test_acknowledgements_do_not_retrieve(self):
        for text in ("yes", "no", "okay", "ஆமா", "இல்லை", "சரி"):
            self.assertTrue(is_short_acknowledgement(text))
            self.assertFalse(should_retrieve_knowledge(text, "tamil"))


class RuntimeIntegrationTests(unittest.TestCase):
    def test_english_custom_voice_is_supported(self):
        with patch.dict(os.environ, {
            "OPENAI_REALTIME_VOICE_ENGLISH": "shimmer",
            "OPENAI_REALTIME_VOICE_ENGLISH_CUSTOM_ID": "voice_english_123",
        }, clear=True):
            self.assertEqual(
                resolve_realtime_voice("english"),
                ({"id": "voice_english_123"}, "custom", "voice_english_123"),
            )

    def test_route_has_real_bilingual_barge_in_and_latest_turn_guard(self):
        source = Path("app/api/openai_realtime.py").read_text(encoding="utf-8")
        self.assertIn("confirm_barge_in", source)
        self.assertIn('"type": "response.cancel"', source)
        self.assertIn('"type": "conversation.item.truncate"', source)
        self.assertIn("clear_audio(stream_sid)", source)
        self.assertIn("interrupted_response_ids", source)
        self.assertIn("event_response_id not in interrupted_response_ids", source)
        self.assertIn("async with response_lock", source)
        self.assertIn("turn_id != latest_customer_turn_id", source)
        self.assertIn("pending_response_items.clear()", source)

    def test_database_metrics_reuse_existing_usage_json(self):
        source = Path("app/api/openai_realtime.py").read_text(encoding="utf-8")
        schema = Path("schema.sql").read_text(encoding="utf-8")
        for metric in (
            "cancelled_assistant_responses",
            "stop_intent_count",
            "callback_intent_count",
            "end_call_intent_count",
            "average_assistant_response_words",
            "maximum_assistant_response_words",
            "short_response_compliance_rate",
        ):
            self.assertIn(metric, source)
        self.assertIn("usage_data LONGTEXT", schema)
        self.assertIn("followup_required BOOLEAN", schema)


class OrganizationNameScopingTests(unittest.TestCase):
    """The opening greeting and system-prompt preambles used to hardcode
    'DigiDara Technologies' for every organization's calls. They now take an
    organization_name, defaulting to 'DigiDara Technologies' so any caller
    that doesn't pass one yet (or DigiDARA's own calls) keeps today's exact
    behavior, while a real customer organization's calls introduce that
    organization instead."""

    def setUp(self):
        self.customer = {"name": "Kumar", "investigated_course": "AI and ML"}
        self.campaign = {"objective": "Follow up on the enquiry."}

    def test_defaults_preserve_digidara_technologies_for_unscoped_callers(self):
        self.assertIn("DigiDara Technologies", build_shared_conversation_policy())
        self.assertIn(
            "DigiDara Technologies",
            build_existing_english_session_instructions(self.customer, self.campaign),
        )
        self.assertIn(
            "DigiDara Technologies",
            build_greeting_instruction("english", self.customer),
        )
        self.assertIn(
            "DigiDara Technologies",
            build_greeting_instruction("tamil", self.customer),
        )

    def test_customer_organization_name_replaces_digidara_everywhere(self):
        shared = build_shared_conversation_policy("Acme Corp")
        system_prompt = build_existing_english_session_instructions(
            self.customer, self.campaign, organization_name="Acme Corp",
        )
        greeting_en = build_greeting_instruction("english", self.customer, organization_name="Acme Corp")
        greeting_ta = build_greeting_instruction("tamil", self.customer, organization_name="Acme Corp")

        for text in (shared, system_prompt, greeting_en, greeting_ta):
            self.assertIn("Acme Corp", text)
            self.assertNotIn("DigiDara", text)

    def test_initial_session_instructions_thread_organization_name_through(self):
        prompt = build_initial_session_instructions(
            "tamil", self.customer, self.campaign, organization_name="Acme Corp",
        )
        self.assertIn("Acme Corp", prompt)
        self.assertNotIn("DigiDara", prompt)

    def test_initial_prompt_metrics_accepts_organization_name(self):
        # Must not raise, and token counts should stay within the same
        # budget regardless of which organization's name is substituted.
        metrics = initial_prompt_metrics(
            "tamil", self.customer, self.campaign, organization_name="Acme Corp",
        )
        self.assertLessEqual(metrics["total_estimated_tokens"], 1200)

    def test_greeting_grammar_avoids_the_possessive_apostrophe_edge_case(self):
        # "DigiDara Technologies'" relies on the name already ending in "s"
        # for a grammatical possessive; a name that doesn't end in "s" (like
        # "Acme Corp") must not read as "Acme Corp'" with a bare apostrophe.
        greeting = build_greeting_instruction("english", self.customer, organization_name="Acme Corp")
        self.assertNotIn("Acme Corp’", greeting)
        self.assertNotIn("Acme Corp'", greeting)


if __name__ == "__main__":
    unittest.main()
