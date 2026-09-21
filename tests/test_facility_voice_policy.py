import unittest

from app.facility.orchestration.voice_policy import (
    FACILITY_VOICE_PROFILE,
    build_facility_greeting_instruction,
    build_facility_voice_session_instructions,
    should_retrieve_facility_knowledge,
)


class FacilityVoicePolicyTests(unittest.TestCase):
    def test_session_prompt_is_facility_only_and_protects_write_confirmation(self):
        prompt = build_facility_voice_session_instructions(
            {"name": "Anika"}, "Nectar Facilities",
            [{"asset_code": "AHU-02", "status": "degraded"}],
            [{"severity": "high", "title": "AHU-02 low airflow"}],
        )
        self.assertEqual("nectar_facility_operations_voice_v1", FACILITY_VOICE_PROFILE)
        self.assertIn("AHU-02: degraded", prompt)
        self.assertIn("explicit confirmation", prompt)
        self.assertIn("Decline subjects outside this operational scope", prompt)
        self.assertNotIn("sales counsellor", prompt.casefold())

    def test_greeting_does_not_reference_legacy_enquiry_content(self):
        greeting = build_facility_greeting_instruction({"name": "Anika"}, "Nectar Facilities")
        self.assertIn("Facility Operations", greeting)
        self.assertIn("Nectar Facilities", greeting)
        self.assertNotIn("enquiry", greeting.casefold())
        self.assertNotIn("AI and ML", greeting)

    def test_retrieval_skips_social_turns_and_keeps_operational_questions(self):
        self.assertFalse(should_retrieve_facility_knowledge("Thanks"))
        self.assertTrue(should_retrieve_facility_knowledge("What should I inspect for AHU low airflow?"))


if __name__ == "__main__":
    unittest.main()
