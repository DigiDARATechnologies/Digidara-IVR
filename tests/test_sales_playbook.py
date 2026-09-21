import unittest

from app.services.sales_playbook import (
    SALES_CONVERSATION_PROFILE,
    consultative_turn_contract,
    enquiry_subject,
    normalize_lead_type,
    sales_context,
    sales_playbook,
)


class LeadRoutingTests(unittest.TestCase):
    def test_imported_leads_route_to_the_correct_sales_journey(self):
        self.assertEqual(
            normalize_lead_type(
                {"internship_or_course": "Internship", "investigated_course": "Data Science"}
            ),
            "internship",
        )
        self.assertEqual(
            normalize_lead_type(
                {"internship_or_course": "Project", "investigated_course": "AI chatbot"}
            ),
            "project",
        )
        self.assertEqual(
            normalize_lead_type(
                {"internship_or_course": "Course", "investigated_course": "AI and ML"}
            ),
            "course",
        )

    def test_greeting_subject_does_not_call_every_lead_a_course(self):
        customer = {
            "internship_or_course": "Project",
            "investigated_course": "College GPT",
        }
        self.assertEqual(enquiry_subject(customer, "english"), "College GPT")
        self.assertEqual(enquiry_subject(customer, "tamil"), "College GPT project")

    def test_sales_context_preserves_imported_details(self):
        context = sales_context(
            {
                "internship_or_course": "Internship",
                "investigated_course": "Generative AI",
                "course_duration": "1 month",
            }
        )
        self.assertIn("Lead type: internship", context)
        self.assertIn("Generative AI", context)
        self.assertIn("1 month", context)


class ConsultativeSalesPolicyTests(unittest.TestCase):
    def test_all_routes_use_one_question_and_safe_closing_rules(self):
        for lead_type in ("Course", "Internship", "Project"):
            playbook = sales_playbook({"internship_or_course": lead_type}, "tamil")
            self.assertIn("ask only one purposeful question", playbook)
            self.assertIn("never invent or quote an amount", playbook)
            self.assertIn("never guarantee employment", playbook)
            self.assertIn("Never claim WhatsApp details were sent", playbook)
            self.assertIn("natural Tamil/Tanglish", playbook)

    def test_each_lead_type_gets_specific_discovery_and_close(self):
        course = sales_playbook({"internship_or_course": "Course"}, "english")
        internship = sales_playbook({"internship_or_course": "Internship"}, "english")
        project = sales_playbook({"internship_or_course": "Project"}, "english")
        self.assertIn("career goal", course)
        self.assertIn("preferred domain", internship)
        self.assertIn("academic/student project or a business", project)
        self.assertEqual(SALES_CONVERSATION_PROFILE, "consultative_education_sales_v2")

    def test_fit_questions_get_personalized_conditional_sales_answers(self):
        for language in ("english", "tamil"):
            contract = consultative_turn_contract(language)
            self.assertIn("FIT QUESTIONS", contract)
            self.assertIn("Never guarantee success", contract)
            self.assertIn("Direct answer first", contract)
            self.assertIn("Do not repeat the previous assistant answer", contract)
        self.assertIn("Will this work for me?", consultative_turn_contract("english"))
        self.assertIn("இந்த course எனக்கு work ஆகுமா?", consultative_turn_contract("tamil"))

    def test_only_english_gets_the_stricter_spoken_length_limit(self):
        english = consultative_turn_contract("english")
        tamil = consultative_turn_contract("tamil")
        self.assertIn("ENGLISH SPOKEN LENGTH LIMIT", english)
        self.assertIn("8–20 spoken words", english)
        self.assertIn("28 words", english)
        self.assertNotIn("ENGLISH SPOKEN LENGTH LIMIT", tamil)


if __name__ == "__main__":
    unittest.main()
