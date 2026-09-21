import unittest
from pathlib import Path

from app.services.call_inactivity import (
    CallInactivityPolicy,
    inactivity_goodbye_instruction,
    inactivity_reprompt_instruction,
)


class CallInactivityPolicyTests(unittest.TestCase):
    def test_silence_reprompts_once_then_hangs_up(self):
        policy = CallInactivityPolicy(reprompt_seconds=15, hangup_seconds=10)

        first_revision = policy.activity_revision
        self.assertEqual(policy.timeout_seconds, 15)
        self.assertEqual(policy.action_after_timeout(first_revision), "reprompt")
        self.assertEqual(policy.timeout_seconds, 10)
        self.assertEqual(policy.action_after_timeout(first_revision), "hangup")

    def test_caller_activity_resets_the_second_timeout(self):
        policy = CallInactivityPolicy(reprompt_seconds=15, hangup_seconds=10)
        old_revision = policy.state_revision
        self.assertEqual(policy.action_after_timeout(old_revision), "reprompt")

        policy.note_activity()

        self.assertEqual(policy.action_after_timeout(old_revision), "activity")
        self.assertFalse(policy.awaiting_final_timeout)
        self.assertEqual(policy.timeout_seconds, 15)
        self.assertEqual(
            policy.action_after_timeout(policy.state_revision), "reprompt"
        )

    def test_assistant_speech_restarts_timer_without_losing_reprompt_phase(self):
        policy = CallInactivityPolicy(reprompt_seconds=15, hangup_seconds=10)
        self.assertEqual(
            policy.action_after_timeout(policy.state_revision), "reprompt"
        )
        running_timer_revision = policy.state_revision

        policy.note_assistant_state_change()

        self.assertEqual(
            policy.action_after_timeout(running_timer_revision), "activity"
        )
        self.assertTrue(policy.awaiting_final_timeout)
        self.assertEqual(policy.timeout_seconds, 10)

    def test_reprompt_and_goodbye_are_bilingual_and_short(self):
        english_reprompt = inactivity_reprompt_instruction("english")
        english_goodbye = inactivity_goodbye_instruction("english")
        tamil_reprompt = inactivity_reprompt_instruction("tamil")
        tamil_goodbye = inactivity_goodbye_instruction("tamil")

        self.assertIn("Are you still there?", english_reprompt)
        self.assertIn("end the call now", english_goodbye)
        self.assertIn("நீங்க இன்னும் லைன்ல இருக்கீங்களா?", tamil_reprompt)
        self.assertIn("call-ஐ முடிக்கிறேன்", tamil_goodbye)
        for instruction in (
            english_reprompt, english_goodbye, tamil_reprompt, tamil_goodbye,
        ):
            self.assertIn("exactly", instruction)

    def test_active_realtime_bridge_owns_the_watchdog(self):
        source = Path("app/api/openai_realtime.py").read_text(encoding="utf-8")
        self.assertIn("async def inactivity_watchdog()", source)
        self.assertIn("note_caller_activity()", source)
        self.assertIn("note_assistant_state_change()", source)
        self.assertIn("CALL_INACTIVITY_REPROMPT_SECONDS", source)
        self.assertIn("CALL_INACTIVITY_HANGUP_SECONDS", source)
        self.assertIn("conversation_end_reason='inactivity_timeout'", source)
        self.assertIn("schedule_graceful_customer_hangup()", source)


if __name__ == "__main__":
    unittest.main()
