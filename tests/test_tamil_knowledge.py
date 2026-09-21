import unittest

from app.livekit_agent.memory_kb import get_fast_context, search
from app.services.knowledge_base_ta import (
    ALL_SEED_DOCS_TA,
    REQUIRED_COLLECTIONS_TA,
)


class TamilKnowledgeParityTests(unittest.TestCase):
    def setUp(self):
        self.documents = [
            document
            for collection in ALL_SEED_DOCS_TA.values()
            for document in collection
        ]
        self.by_canonical_id = {
            document["metadata"]["canonical_id"]: document
            for document in self.documents
        }

    def test_every_required_collection_has_reviewed_spoken_tamil(self):
        self.assertEqual(set(ALL_SEED_DOCS_TA), set(REQUIRED_COLLECTIONS_TA))
        for collection in REQUIRED_COLLECTIONS_TA:
            self.assertTrue(ALL_SEED_DOCS_TA[collection], collection)
        for document in self.documents:
            metadata = document["metadata"]
            self.assertEqual(metadata["language"], "ta")
            self.assertEqual(metadata["register"], "spoken_tamil_nadu")
            self.assertEqual(metadata["source"], "user_master_knowledge_tamil")
            self.assertNotIn("\ufffd", document["text"])
            self.assertNotIn("à®", document["text"])

    def test_critical_english_facts_have_tamil_counterparts(self):
        expected = {
            "company_overview",
            "founder_profile",
            "courses_overview",
            "course_data_science",
            "course_ai_ml",
            "course_genai_agentic",
            "course_digital_marketing",
            "course_python_fullstack",
            "course_ai_managers",
            "internship_overview",
            "internship_tracks",
            "services_overview",
            "products_overview",
            "career_support_overview",
            "pricing_info",
            "contact_details",
            "book_demo",
            "enrollment_process",
            "company_certifications",
            "company_unique",
            "company_impact",
            "founder_motivation",
            "founder_ai_agents",
            "courses_beginner_fit",
            "courses_projects_certificate",
            "courses_group_corporate",
            "internship_beginner_fit",
            "internship_project_examples",
            "service_digital_marketing",
            "service_chatbot",
            "service_ai_agents",
            "service_consulting",
            "service_results",
            "service_industries",
            "service_frameworks",
            "product_ai_crm",
            "product_lead_flux",
            "product_ai_academy",
            "product_careermate",
            "product_college_gpts",
            "product_automation",
            "career_ai_india",
            "career_testimonials",
            "contact_web_channels",
        }
        self.assertTrue(expected.issubset(self.by_canonical_id))
        self.assertGreaterEqual(len(self.documents), 45)

    def test_fast_context_always_keeps_mutable_fact_guardrails(self):
        context = get_fast_context("ta")
        self.assertIn("[pricing:pricing_info]", context)
        self.assertIn("எந்த amount-யும் guess பண்ணக்கூடாது", context)
        self.assertIn("[contact:contact_details]", context)
        self.assertIn("[contact:book_demo]", context)
        self.assertIn("[enrollment:enrollment_process]", context)
        self.assertIn("[courses:courses_overview]", context)
        self.assertLessEqual(len(context), 7000)

    def test_common_tanglish_queries_retrieve_the_right_fact(self):
        self.assertIn("fees", search("course fees evlo?", "ta", top_k=1).lower())
        self.assertIn("office", search("office enga iruku?", "ta", top_k=1).lower())
        self.assertIn("placement", search("job placement irukka?", "ta", top_k=1).lower())
        self.assertIn("beginner", search("beginner naan course join pannalama?", "ta", top_k=1).lower())
        self.assertIn("chatbot", search("business ku whatsapp chatbot pannuveengala?", "ta", top_k=1).lower())
        self.assertIn("lead flux", search("Lead Flux enna product?", "ta", top_k=1).lower())


if __name__ == "__main__":
    unittest.main()
