import unittest

from app.services.conversation_end import (
    farewell_instruction,
    is_customer_goodbye,
)


class CustomerGoodbyeTests(unittest.TestCase):
    def test_english_explicit_goodbyes_end_the_call(self):
        for text in (
            "Bye",
            "Okay, thank you. Bye.",
            "Thanks, goodbye",
            "That's all, bye",
            "Please end the call",
            "Talk to you later",
        ):
            with self.subTest(text=text):
                self.assertTrue(is_customer_goodbye(text, "english"))

    def test_tamil_and_tanglish_explicit_goodbyes_end_the_call(self):
        for text in (
            "சரிங்க, நன்றி பை",
            "நன்றி வணக்கம்",
            "அப்புறம் பேசலாம்",
            "போன் வைக்கிறேன்",
            "call cut pannunga",
            "seri nandri bye",
        ):
            with self.subTest(text=text):
                self.assertTrue(is_customer_goodbye(text, "tamil"))

    def test_negative_question_cut_forms_end_the_call(self):
        """"Won't you cut/end it" phrasing — a real customer asked this and it
        was previously missed because only imperative "cut the call" forms
        were recognized."""
        for text, language in (
            ("மீனே கட்பணமாட்டியா?", "tamil"),
            ("நீயே கட்பணமாட்டியா", "tamil"),
            ("Wont you end the call", "english"),
            ("Can you cut the call", "english"),
        ):
            with self.subTest(text=text):
                self.assertTrue(is_customer_goodbye(text, language))

    def test_unrelated_questions_do_not_falsely_end_the_call(self):
        for text, language in (
            ("இது எப்போ முடியும்?", "tamil"),
            ("Fees எவ்வளவு?", "tamil"),
            ("Can you tell me the batch timing", "english"),
        ):
            with self.subTest(text=text):
                self.assertFalse(is_customer_goodbye(text, language))

    def test_polite_thanks_do_not_end_an_active_conversation(self):
        for text in (
            "Thank you",
            "Thanks",
            "Thank you so much",
            "நன்றி",
            "ரொம்ப நன்றி",
            "nandri",
        ):
            with self.subTest(text=text):
                self.assertFalse(is_customer_goodbye(text, "tamil"))

    def test_farewell_has_no_followup_question(self):
        for language in ("english", "tamil"):
            instruction = farewell_instruction(language)
            self.assertIn("Do not ask a question", instruction)
            self.assertNotIn("?", instruction)


if __name__ == "__main__":
    unittest.main()
