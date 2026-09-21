import unittest

from app.services.call_summary import (
    build_call_summary,
    fallback_summary,
    parse_analysis_response,
)


class AnalysisParsingTests(unittest.TestCase):
    def test_parses_fenced_json_with_surrounding_text(self):
        raw = 'Result:\n```json\n{"summary":"Customer asked about fees and plans to join.","quick_summary":"Interested in course fees"}\n```'
        parsed = parse_analysis_response(raw)
        self.assertEqual(parsed["quick_summary"], "Interested in course fees")

    def test_malformed_provider_output_does_not_leak_to_ui(self):
        full, quick = build_call_summary(
            {},
            "assistant: Welcome\nuser: AI course fees எவ்வளவு?",
            "completed",
        )
        self.assertIn("AI course fees", full)
        self.assertIn("Customer need:", full)
        self.assertIn("Outcome:", full)
        self.assertIn("Next action:", full)
        self.assertNotIn("{", quick)


class SummaryFormattingTests(unittest.TestCase):
    def test_adds_explicit_next_action_to_good_analysis(self):
        full, quick = build_call_summary(
            {
                "customer_need": "Asked about the AI course fee",
                "discussion": "Explained the project-based course and career support",
                "outcome": "Interested and waiting for the exact fee",
                "quick_summary": "Interested in AI course fees",
                "next_action": "Counsellor should confirm the exact fee",
            },
            "user: What is the fee?",
            "completed",
        )
        self.assertEqual(full.splitlines(), [
            "Customer need: Asked about the AI course fee",
            "Discussion: Explained the project-based course and career support",
            "Outcome: Interested and waiting for the exact fee",
            "Next action: Counsellor should confirm the exact fee",
        ])
        self.assertEqual(quick, "Interested in AI course fees")

    def test_empty_call_has_clear_summary(self):
        full, quick = fallback_summary("assistant: Welcome", "no-answer")
        self.assertIn("No meaningful customer response", full)
        self.assertEqual(quick, "No meaningful customer response captured")

    def test_full_transcript_fallback_uses_need_and_assistant_discussion(self):
        transcript = "\n".join([
            "assistant: Welcome to DigiDARA.",
            "customer: I am a final year computer science student with basic Python knowledge and need an AI and ML course for an IT job.",
            "assistant: The AI and ML course is project based with practical labs, a capstone, certificate, and career support.",
            "customer: I want to visit your company and get the full details.",
            "customer: Thank you. Bye.",
        ])
        full, _ = fallback_summary(transcript, "completed")
        self.assertEqual(len(full.splitlines()), 4)
        self.assertIn("final year computer science student", full)
        self.assertIn("project based", full)
        self.assertIn("visit", full)


if __name__ == "__main__":
    unittest.main()
