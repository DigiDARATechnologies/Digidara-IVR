"""Pre-rendered prompts used for inbound call routing states (unconfigured DID, closed office)."""

from app.services.ivr_prompt_audio import ensure_prompt_audio


UNCONFIGURED_TEXT = "Sorry, inbound calling is not configured yet."
CLOSED_TEXT = "Sorry, our office is currently closed. Please call back during business hours."


def unconfigured_audio_path():
    return ensure_prompt_audio(UNCONFIGURED_TEXT)


def closed_audio_path():
    return ensure_prompt_audio(CLOSED_TEXT)
