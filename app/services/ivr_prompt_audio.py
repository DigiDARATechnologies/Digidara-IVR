"""Render and cache a short tenant IVR audio prompt without carrier TTS."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import requests

from app.services.language_prompt_audio import language_prompt_tts_payload, normalize_language_prompt_wav


PROMPT_DIRECTORY = Path(__file__).resolve().parents[2] / "static" / "ivr_prompts"


def _path(prompt: str) -> Path:
    digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    return PROMPT_DIRECTORY / f"{digest}.wav"


def ensure_prompt_audio(prompt: str) -> Path:
    path = _path(prompt)
    if path.exists() and path.stat().st_size > 0:
        return path
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    response = requests.post(
        "https://api.openai.com/v1/audio/speech",
        headers={"Authorization": f"Bearer {api_key}"},
        json=language_prompt_tts_payload(prompt), timeout=30,
    )
    response.raise_for_status()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(normalize_language_prompt_wav(response.content))
    return path
