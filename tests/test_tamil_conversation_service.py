import os
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.tamil_conversation_service import (
    build_campaign_context,
    build_customer_context,
    build_greeting_instruction,
    build_initial_session_instructions,
    build_knowledge_context,
    build_static_tamil_policy,
    build_turn_context,
    compact_campaign_prompt,
    compact_customer_memory,
    initial_prompt_metrics,
    resolve_realtime_model,
    resolve_realtime_voice,
    should_retrieve_knowledge,
    validate_custom_voice_id,
)


class TamilPromptArchitectureTests(unittest.TestCase):
    def setUp(self):
        self.customer = {
            "name": "குமார்",
            "language": "tamil",
            "investigated_course": "AI & ML course",
            "internship_or_course": "course",
        }
        self.campaign = {
            "objective": "Understand the requirement and agree a next step.",
            "ai_prompt": "Fees are confirmed by counsellor.\nFees are confirmed by counsellor.\nAsk {customer_name} about the 2026 batch.",
        }

    def test_static_policy_is_compact_and_enforces_short_spoken_tamil(self):
        metrics = initial_prompt_metrics(self.customer, self.campaign)
        # This had zero headroom at 700 even before the off-topic guardrail
        # sentence (an explicit production requirement) was added to the
        # shared policy; raised just enough to fit it.
        self.assertLessEqual(metrics["static_policy_tokens"], 740)
        policy = build_static_tamil_policy()
        self.assertIn("Prefer one short sentence", policy)
        self.assertIn("Newsreader", policy)

    def test_initial_session_has_no_full_knowledge_base(self):
        prompt = build_initial_session_instructions(
            self.customer, self.campaign, {"summary": "Asked about evening timing"}
        )
        self.assertNotIn("FACTUAL REFERENCE", prompt)
        self.assertNotIn("APPROVED KNOWLEDGE", prompt)
        self.assertLessEqual(initial_prompt_metrics(self.customer, self.campaign)["total_estimated_tokens"], 1200)

    def test_greeting_is_short_and_has_no_knowledge(self):
        greeting = build_greeting_instruction(self.customer)
        self.assertIn("AI voice assistant", greeting)
        self.assertIn("AI & ML course", greeting)
        self.assertNotIn("FACTUAL REFERENCE", greeting)

    def test_campaign_is_facts_not_script_and_deduplicated(self):
        compacted = compact_campaign_prompt(self.campaign["ai_prompt"])
        self.assertEqual(compacted.count("Fees are confirmed"), 1)
        self.assertIn("{customer_name}", compacted)
        self.assertIn("2026", compacted)
        context = build_campaign_context(self.campaign)
        self.assertIn("FACTS AND GOALS", context)
        self.assertIn("untrusted_campaign_content", context)

    def test_knowledge_is_deduplicated_and_limited(self):
        context = build_knowledge_context(
            ["Fees must be confirmed.", "Fees must be confirmed.", "Batch timing is verified."],
            max_chars=600,
        )
        self.assertEqual(context.count("Fees must be confirmed."), 1)
        self.assertLessEqual(len(context), 1100)
        self.assertIn("DO NOT READ VERBATIM", context)

    def test_customer_memory_is_compact(self):
        memory = {"summary": "x" * 1000, "private_field": "must not appear"}
        self.assertLessEqual(len(compact_customer_memory(memory)), 700)
        self.assertNotIn("private_field", build_customer_context(self.customer, memory))

    def test_turn_context_enforces_short_non_repeating_reply(self):
        context = build_turn_context("fee evlo?", "Fees are counsellor-confirmed.", "Old answer")
        self.assertIn("one or two short", context)
        self.assertIn("Do not repeat", context)

    def test_runtime_does_not_log_full_prompt_text(self):
        source = Path("app/api/openai_realtime.py").read_text(encoding="utf-8")
        self.assertNotIn("print(instructions)", source)
        self.assertNotIn("print(prompt)", source)
        self.assertIn("prompt metrics", source)

    def test_existing_database_schema_is_idempotently_supported(self):
        schema = Path("schema.sql").read_text(encoding="utf-8")
        initializer = Path("app/database/db.py").read_text(encoding="utf-8")
        self.assertIn("information_schema.COLUMNS", schema)
        self.assertIn("cached_input_audio_tokens", schema)
        self.assertIn("cached_input_text_tokens", schema)
        self.assertIn("SHOW COLUMNS FROM realtime_usage", initializer)
        self.assertIn("utf8mb4", schema)


class TamilRetrievalTests(unittest.TestCase):
    def test_social_and_administrative_turns_skip_retrieval(self):
        for text in (
            "ஹலோ", "சரி", "ஆமா", "இல்லை", "I am busy later call",
            "WhatsAppல details அனுப்புங்க", "Englishல பேசுங்க", "thank you",
        ):
            with self.subTest(text=text):
                self.assertFalse(should_retrieve_knowledge(text))

    def test_factual_tamil_and_tanglish_turns_retrieve(self):
        for text in (
            "Fees எவ்வளவு?", "fee evlo?", "Evening batch இருக்கா?",
            "course duration evlo months?", "Placement guarantee இருக்கா?",
            "Next batch exact date என்ன?", "Discount இருக்கா?",
        ):
            with self.subTest(text=text):
                self.assertTrue(should_retrieve_knowledge(text))


class RealtimeResolutionTests(unittest.TestCase):
    def test_model_resolution_order(self):
        with patch.dict(os.environ, {
            "OPENAI_REALTIME_MODEL": "generic",
            "OPENAI_REALTIME_MODEL_TAMIL": "tamil-model",
            "OPENAI_REALTIME_MODEL_ENGLISH": "english-model",
        }, clear=True):
            self.assertEqual(resolve_realtime_model("tamil"), "tamil-model")
            self.assertEqual(resolve_realtime_model("english"), "english-model")
        with patch.dict(os.environ, {"OPENAI_REALTIME_MODEL": "generic"}, clear=True):
            self.assertEqual(resolve_realtime_model("tamil"), "generic")
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                resolve_realtime_model("tamil")

    def test_custom_voice_precedence_and_fallback(self):
        with patch.dict(os.environ, {
            "OPENAI_REALTIME_VOICE_TAMIL": "marin",
            "OPENAI_REALTIME_VOICE_TAMIL_CUSTOM_ID": "voice_tamil123",
        }, clear=True):
            voice, voice_type, label = resolve_realtime_voice("tamil")
            self.assertEqual(voice, {"id": "voice_tamil123"})
            self.assertEqual((voice_type, label), ("custom", "voice_tamil123"))
        with patch.dict(os.environ, {
            "OPENAI_REALTIME_VOICE_TAMIL": "marin",
        }, clear=True):
            self.assertEqual(resolve_realtime_voice("tamil"), ("marin", "built_in", "marin"))

    def test_rejects_paths_urls_and_foreign_ids(self):
        self.assertFalse(validate_custom_voice_id("C:\\voices\\tamil.wav"))
        self.assertFalse(validate_custom_voice_id("https://example.com/tamil.mp3"))
        self.assertFalse(validate_custom_voice_id("21m00Tcm4TlvDq8ikWAM"))
        self.assertTrue(validate_custom_voice_id("voice_tamil_123"))

    def test_voice_is_resolved_before_first_response(self):
        source = Path("app/api/openai_realtime.py").read_text(encoding="utf-8")
        self.assertLess(
            source.index("resolve_realtime_voice(language)"),
            source.index('"type": "session.update"'),
        )
        self.assertLess(
            source.index('"type": "session.update"'),
            source.index('"type": "response.create"'),
        )


if __name__ == "__main__":
    unittest.main()
