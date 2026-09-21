"""Pre-rendered English prompts used only for the staff-side transfer flow."""

from app.services.ivr_prompt_audio import ensure_prompt_audio


CONFIRM_TEXT = "Incoming DigiDARA customer call. Press 1 to accept."
FALLBACK_TEXT = "Our team is unavailable. We have saved your callback request."


def confirmation_audio_path():
    return ensure_prompt_audio(CONFIRM_TEXT)


def fallback_audio_path():
    return ensure_prompt_audio(FALLBACK_TEXT)
