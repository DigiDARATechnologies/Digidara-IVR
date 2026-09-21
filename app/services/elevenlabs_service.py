"""
ElevenLabs TTS service — uses httpx directly (NO elevenlabs SDK).

Why no SDK: The official elevenlabs Python SDK installs files with deeply
nested paths (pronunciation_dictionaries/rules/types/...) that exceed
Windows' default 260-character path limit, causing installation to fail
with OSError on Windows machines without Long Path support enabled.

This implementation calls the ElevenLabs REST API directly using httpx
(already in requirements.txt for Sarvam) — zero new dependencies,
no path issues, same speed and quality.

English calls use ElevenLabs (~150-250ms TTS).
Tamil calls use Sarvam (ElevenLabs has no Tamil support).
"""

import hashlib
import io
import os
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv(
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env")),
    override=True,
)

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
DEFAULT_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # Rachel
MODEL_ID = os.getenv("ELEVENLABS_MODEL_ID", "eleven_turbo_v2_5")

ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

# Shared pooled HTTP clients (same pattern as sarvam_service.py)
_async_client: Optional[httpx.AsyncClient] = None
_sync_client: Optional[httpx.Client] = None

# In-memory TTS cache
_CACHE: dict[str, bytes] = {}
_CACHE_MAX = 300


def _is_configured() -> bool:
    return bool(ELEVENLABS_API_KEY) and ELEVENLABS_API_KEY != "your_elevenlabs_api_key_here"


def _cache_key(text: str, voice_id: str) -> str:
    return hashlib.sha1(f"{voice_id}::{text.strip()}".encode()).hexdigest()


def _get_sync_client() -> httpx.Client:
    global _sync_client
    if _sync_client is None:
        _sync_client = httpx.Client(
            timeout=httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0),
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )
    return _sync_client


def _get_async_client() -> httpx.AsyncClient:
    global _async_client
    if _async_client is None:
        _async_client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0),
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )
    return _async_client


def _build_payload(text: str) -> dict:
    return {
        "text": text,
        "model_id": MODEL_ID,
        "output_format": "wav_8000",       # 8kHz WAV — Twilio native, zero conversion
        "optimize_streaming_latency": 4,   # max latency optimization
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.0,
            "use_speaker_boost": True,
        },
    }


def text_to_speech_elevenlabs(
    text: str,
    voice_id: Optional[str] = None,
) -> bytes:
    """
    Synchronous ElevenLabs TTS via direct httpx — used in background threads
    (greeting pre-generation runs outside the asyncio event loop).
    Falls back to Sarvam TTS if ElevenLabs is not configured.
    """
    if not _is_configured():
        from app.services.sarvam_service import text_to_speech
        return text_to_speech(text, language_code="en-IN")

    vid = voice_id or DEFAULT_VOICE_ID
    key = _cache_key(text, vid)
    if key in _CACHE:
        return _CACHE[key]

    url = ELEVENLABS_TTS_URL.format(voice_id=vid)
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/wav",
    }

    try:
        client = _get_sync_client()
        response = client.post(url, json=_build_payload(text), headers=headers)
        if response.status_code in (200, 201):
            audio_bytes = response.content
            if len(_CACHE) >= _CACHE_MAX:
                _CACHE.pop(next(iter(_CACHE)))
            _CACHE[key] = audio_bytes
            return audio_bytes
        else:
            print(f"[ElevenLabs TTS] HTTP {response.status_code}: {response.text[:200]}")
            raise RuntimeError(f"ElevenLabs API returned {response.status_code}")
    except Exception as e:
        print(f"[ElevenLabs TTS] Error: {e} — falling back to Sarvam")
        from app.services.sarvam_service import text_to_speech
        return text_to_speech(text, language_code="en-IN")


async def text_to_speech_elevenlabs_async(
    text: str,
    voice_id: Optional[str] = None,
) -> bytes:
    """
    Async ElevenLabs TTS via direct httpx — used in the live call loop.
    Falls back to Sarvam async TTS if ElevenLabs is not configured.
    """
    if not _is_configured():
        from app.services.sarvam_service import text_to_speech_async
        return await text_to_speech_async(text, language_code="en-IN")

    vid = voice_id or DEFAULT_VOICE_ID
    key = _cache_key(text, vid)
    if key in _CACHE:
        return _CACHE[key]

    url = ELEVENLABS_TTS_URL.format(voice_id=vid)
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/wav",
    }

    try:
        client = _get_async_client()
        response = await client.post(url, json=_build_payload(text), headers=headers)
        if response.status_code in (200, 201):
            audio_bytes = response.content
            if len(_CACHE) >= _CACHE_MAX:
                _CACHE.pop(next(iter(_CACHE)))
            _CACHE[key] = audio_bytes
            return audio_bytes
        else:
            print(f"[ElevenLabs TTS async] HTTP {response.status_code}: {response.text[:200]}")
            raise RuntimeError(f"ElevenLabs API returned {response.status_code}")
    except Exception as e:
        print(f"[ElevenLabs TTS async] Error: {e} — falling back to Sarvam")
        from app.services.sarvam_service import text_to_speech_async
        return await text_to_speech_async(text, language_code="en-IN")


def is_available() -> bool:
    return _is_configured()
