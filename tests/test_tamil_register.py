import unittest

from app.services.tamil_register import (
    detect_tamil_register,
    tamil_register_instruction,
)


class TamilRegisterTests(unittest.TestCase):
    def test_detects_tamil_dominant_turn(self):
        self.assertEqual(
            detect_tamil_register("எனக்கு இந்த கோர்ஸ் பற்றி முழுசா சொல்லுங்க"),
            "tamil",
        )
        self.assertEqual(
            detect_tamil_register("எனக்கு AI course வேணும்"),
            "tamil",
        )

    def test_detects_spoken_tanglish_transcript(self):
        self.assertEqual(
            detect_tamil_register("enakku AI course fees and duration sollunga"),
            "tanglish",
        )

    def test_detects_mixed_register(self):
        self.assertEqual(
            detect_tamil_register(
                "எனக்கு AI course online batch timing பற்றி சொல்லுங்க"
            ),
            "mixed",
        )

    def test_register_instructions_preserve_tamil_identity(self):
        tamil = tamil_register_instruction("தமிழ்ல பேசுங்க")
        tanglish = tamil_register_instruction("tanglish la explain pannunga")
        mixed = tamil_register_instruction("இந்த course online mode இருக்கா")
        self.assertIn("mainly in natural spoken Tamil", tamil)
        self.assertIn("Tamil Nadu Tanglish", tanglish)
        self.assertIn("balanced spoken Tamil/Tanglish", mixed)
        self.assertIn("audio as the primary signal", tamil)


if __name__ == "__main__":
    unittest.main()
