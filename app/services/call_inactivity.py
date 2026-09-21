"""State and bilingual response instructions for caller inactivity handling."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CallInactivityPolicy:
    """Track the two-stage silence flow without coupling it to a provider."""

    reprompt_seconds: int
    hangup_seconds: int
    activity_revision: int = 0
    state_revision: int = 0
    awaiting_final_timeout: bool = False

    @property
    def timeout_seconds(self) -> int:
        return (
            self.hangup_seconds
            if self.awaiting_final_timeout
            else self.reprompt_seconds
        )

    def note_activity(self) -> None:
        self.activity_revision += 1
        self.state_revision += 1
        self.awaiting_final_timeout = False

    def note_assistant_state_change(self) -> None:
        """Invalidate a running timer without resetting reprompt progress."""
        self.state_revision += 1

    def action_after_timeout(self, observed_revision: int) -> str:
        """Return ``activity``, ``reprompt``, or ``hangup`` for a timer expiry."""
        if observed_revision != self.state_revision:
            return "activity"
        if not self.awaiting_final_timeout:
            self.awaiting_final_timeout = True
            return "reprompt"
        return "hangup"


def inactivity_reprompt_instruction(language: str) -> str:
    if language == "tamil":
        return (
            "The customer has been silent. Say exactly this one short spoken-Tamil "
            "sentence, then wait without adding anything: "
            '"நீங்க இன்னும் லைன்ல இருக்கீங்களா?"'
        )
    return (
        "The customer has been silent. Say exactly this one short English sentence, "
        'then wait without adding anything: "Are you still there?"'
    )


def inactivity_goodbye_instruction(language: str) -> str:
    if language == "tamil":
        return (
            "The customer did not respond after the silence check. Say exactly this "
            "short spoken-Tamil goodbye and nothing else: "
            '"பதில் வராததால் இப்போ call-ஐ முடிக்கிறேன். நன்றி."'
        )
    return (
        "The customer did not respond after the silence check. Say exactly this "
        "short English goodbye and nothing else: "
        '"I haven\'t heard from you, so I\'ll end the call now. Thank you."'
    )
