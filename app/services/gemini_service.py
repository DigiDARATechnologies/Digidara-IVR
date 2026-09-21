"""
Gemini Tamil STT/TTS service.

This module provides the active Tamil STT/TTS path. English TTS remains in
elevenlabs_service.py.
"""

import base64
import hashlib
import os
import time
import wave
from io import BytesIO
from typing import Any, AsyncIterable, Awaitable, Callable, Dict, Optional

from dotenv import load_dotenv
import httpx

load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env")), override=True)

def _load_api_keys() -> list[str]:
    raw_keys = []
    raw_keys.extend((os.getenv("GEMINI_API_KEYS") or "").replace(";", ",").split(","))
    raw_keys.append(os.getenv("GEMINI_API_KEY") or "")
    raw_keys.append(os.getenv("GOOGLE_API_KEY") or "")
    keys = []
    seen = set()
    placeholders = {"", "your_gemini_api_key_here", "your_google_api_key_here", "your_gemini_api_key"}
    for raw in raw_keys:
        key = raw.strip()
        if key in placeholders or key in seen:
            continue
        seen.add(key)
        keys.append(key)
    return keys


API_KEYS = _load_api_keys()
api_key = API_KEYS[0] if API_KEYS else ""
TTS_MODEL = os.getenv("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")
STT_MODEL = os.getenv("GEMINI_STT_MODEL", "gemini-2.5-flash")
DEFAULT_TAMIL_VOICE = os.getenv("TAMIL_TTS_SPEAKER", os.getenv("GEMINI_TAMIL_VOICE", "Kore"))
VALID_GEMINI_VOICES = {
    "Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Leda", "Orus", "Aoede",
    "Callirrhoe", "Autonoe", "Enceladus", "Iapetus", "Umbriel", "Algieba",
    "Despina", "Erinome", "Algenib", "Rasalgethi", "Laomedeia", "Achernar",
    "Alnilam", "Schedar", "Gacrux", "Pulcherrima", "Achird", "Zubenelgenubi",
    "Vindemiatrix", "Sadachbia", "Sadaltager", "Sulafat",
}
API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

_async_client: Optional[httpx.AsyncClient] = None
_sync_client: Optional[httpx.Client] = None
_TTS_CACHE: Dict[str, bytes] = {}
_TTS_CACHE_MAX_ENTRIES = 256
_tts_disabled_until_by_key: Dict[str, float] = {}
_stt_disabled_until_by_key: Dict[str, float] = {}
_QUOTA_COOLDOWN_SECONDS = 300


def _get_async_client() -> httpx.AsyncClient:
    global _async_client
    if _async_client is None:
        _async_client = httpx.AsyncClient(
            http2=False,
            timeout=httpx.Timeout(connect=5.0, read=20.0, write=5.0, pool=5.0),
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )
    return _async_client


def _get_sync_client() -> httpx.Client:
    global _sync_client
    if _sync_client is None:
        _sync_client = httpx.Client(
            timeout=httpx.Timeout(connect=5.0, read=20.0, write=5.0, pool=5.0),
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )
    return _sync_client


def _cache_key(text: str, language_code: str, speaker: str) -> str:
    raw = f"{language_code}|{speaker}|{text}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _gemini_voice(speaker: Optional[str]) -> str:
    requested = (speaker or os.getenv("TAMIL_TTS_SPEAKER") or os.getenv("GEMINI_TAMIL_VOICE") or DEFAULT_TAMIL_VOICE or "Kore").strip()
    if requested in VALID_GEMINI_VOICES:
        return requested
    print(f"[Gemini TTS] Voice '{requested}' is not a Gemini voice; using Kore.")
    return "Kore"


def _spoken_tamil_text(text: str) -> str:
    replacements = {
        "DigiDara Technologies": "டிஜிடாரா டெக்னாலஜிஸ்",
        "DigiDara": "டிஜிடாரா",
        "AI and Machine Learning": "ஏ ஐ மற்றும் மெஷின் லெர்னிங்",
        "Machine Learning": "மெஷின் லெர்னிங்",
        "WhatsApp": "வாட்ஸ்அப்",
        "course": "கோர்ஸ்",
        "Course": "கோர்ஸ்",
        "details": "டீடெயில்ஸ்",
        "Details": "டீடெயில்ஸ்",
        "share": "ஷேர்",
        "Share": "ஷேர்",
        "reminder call": "ரிமைண்டர் கால்",
        "AI": "ஏ ஐ",
    }
    spoken = text
    for old, new in replacements.items():
        spoken = spoken.replace(old, new)
    return spoken


def _endpoint(model: str, key: str) -> str:
    return f"{API_BASE}/{model}:generateContent?key={key}"


def _require_key() -> None:
    if not API_KEYS:
        raise ValueError("GEMINI_API_KEY, GEMINI_API_KEYS, or GOOGLE_API_KEY is not configured in the environment.")


def _key_label(key: str) -> str:
    return f"...{key[-6:]}" if len(key) > 6 else "***"


def _available_keys(kind: str) -> list[str]:
    disabled = _tts_disabled_until_by_key if kind == "TTS" else _stt_disabled_until_by_key
    now = time.time()
    return [key for key in API_KEYS if now >= disabled.get(key, 0.0)]


def _disable_key(kind: str, key: str) -> None:
    disabled = _tts_disabled_until_by_key if kind == "TTS" else _stt_disabled_until_by_key
    disabled[key] = time.time() + _QUOTA_COOLDOWN_SECONDS


async def _post_gemini_async(kind: str, model: str, payload: Dict[str, Any]) -> httpx.Response:
    _require_key()
    keys = _available_keys(kind)
    if not keys:
        raise _gemini_only_error(kind, "All configured Gemini keys are cooling down after quota/API failures.")
    last_error = ""
    for key in keys:
        response = await _get_async_client().post(_endpoint(model, key), json=payload)
        if response.status_code in (200, 201):
            return response
        last_error = f"HTTP {response.status_code}: {response.text[:300]}"
        print(f"Gemini {kind} failed for key {_key_label(key)} ({response.status_code}): {response.text[:300]}")
        if response.status_code == 429:
            _disable_key(kind, key)
            continue
    raise _gemini_only_error(kind, last_error)


def _post_gemini_sync(kind: str, model: str, payload: Dict[str, Any]) -> httpx.Response:
    _require_key()
    keys = _available_keys(kind)
    if not keys:
        raise _gemini_only_error(kind, "All configured Gemini keys are cooling down after quota/API failures.")
    last_error = ""
    for key in keys:
        response = _get_sync_client().post(_endpoint(model, key), json=payload)
        if response.status_code in (200, 201):
            return response
        last_error = f"HTTP {response.status_code}: {response.text[:300]}"
        print(f"Gemini {kind} failed for key {_key_label(key)} ({response.status_code}): {response.text[:300]}")
        if response.status_code == 429:
            _disable_key(kind, key)
            continue
    raise _gemini_only_error(kind, last_error)


def _as_wav(audio_bytes: bytes, sample_rate: int = 24000) -> bytes:
    if audio_bytes.startswith(b"RIFF"):
        return audio_bytes
    buf = BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(audio_bytes)
    return buf.getvalue()


def _extract_inline_audio(data: Dict[str, Any]) -> bytes:
    for candidate in data.get("candidates", []):
        content = candidate.get("content") or {}
        for part in content.get("parts", []):
            inline_data = part.get("inlineData") or part.get("inline_data") or {}
            encoded = inline_data.get("data")
            if encoded:
                return base64.b64decode(encoded)
    raise RuntimeError(f"No audio returned in Gemini TTS response: {data}")


def _extract_text(data: Dict[str, Any]) -> str:
    parts_text = []
    for candidate in data.get("candidates", []):
        content = candidate.get("content") or {}
        for part in content.get("parts", []):
            if part.get("text"):
                parts_text.append(part["text"])
    return " ".join(parts_text).strip()


def _safe_log_text(text: str) -> str:
    return (text or "").encode("ascii", errors="backslashreplace").decode("ascii")


def _gemini_only_error(kind: str, detail: str) -> RuntimeError:
    return RuntimeError(f"Gemini {kind} unavailable; Tamil is configured as Gemini-only. {detail}")


def _tts_payload(text: str, language_code: str, speaker: str) -> Dict[str, Any]:
    spoken_text = _spoken_tamil_text(text) if language_code == "ta-IN" else text
    prompt = (
        "Speak this exactly in natural spoken Tamil suitable for a phone call. "
        "Keep English course/product names natural if present. Text: "
        f"{spoken_text}"
    )
    return {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {
                        "voiceName": _gemini_voice(speaker),
                    }
                }
            },
        },
    }


def _stt_payload(audio_bytes: bytes, language_code: str) -> Dict[str, Any]:
    encoded = base64.b64encode(audio_bytes).decode("ascii")
    expected = "English en-IN" if (language_code or "").lower().startswith("en") else "Tamil ta-IN, possibly with common Tanglish/English course words"
    return {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": (
                            "Transcribe this phone-call audio. Return only the spoken words, "
                            f"no explanation. The expected language is {expected}."
                        )
                    },
                    {"inlineData": {"mimeType": "audio/wav", "data": encoded}},
                ],
            }
        ],
        "generationConfig": {"responseModalities": ["TEXT"]},
    }


async def text_to_speech_async(
    text: str,
    language_code: str = "ta-IN",
    speaker: Optional[str] = None,
    pace: Optional[float] = None,
    hotwords: Optional[list[str]] = None,
) -> bytes:
    """Async Gemini TTS. Returns WAV bytes."""
    _require_key()
    speaker = _gemini_voice(speaker)
    cache_key = _cache_key(text, language_code, speaker)
    cached = _TTS_CACHE.get(cache_key)
    if cached is not None:
        return cached

    response = await _post_gemini_async("TTS", TTS_MODEL, _tts_payload(text, language_code, speaker))

    try:
        audio = _as_wav(_extract_inline_audio(response.json()))
    except Exception as err:
        print(f"Gemini TTS returned no usable audio: {err}")
        raise _gemini_only_error("TTS", str(err))
    if len(_TTS_CACHE) >= _TTS_CACHE_MAX_ENTRIES:
        _TTS_CACHE.pop(next(iter(_TTS_CACHE)))
    _TTS_CACHE[cache_key] = audio
    return audio


def text_to_speech(
    text: str,
    language_code: str = "ta-IN",
    speaker: Optional[str] = None,
    pace: Optional[float] = None,
    hotwords: Optional[list[str]] = None,
) -> bytes:
    """Sync Gemini TTS wrapper for existing background greeting generation."""
    _require_key()
    speaker = _gemini_voice(speaker)
    cache_key = _cache_key(text, language_code, speaker)
    cached = _TTS_CACHE.get(cache_key)
    if cached is not None:
        return cached

    response = _post_gemini_sync("TTS", TTS_MODEL, _tts_payload(text, language_code, speaker))

    try:
        audio = _as_wav(_extract_inline_audio(response.json()))
    except Exception as err:
        print(f"Gemini TTS returned no usable audio: {err}")
        raise _gemini_only_error("TTS", str(err))
    if len(_TTS_CACHE) >= _TTS_CACHE_MAX_ENTRIES:
        _TTS_CACHE.pop(next(iter(_TTS_CACHE)))
    _TTS_CACHE[cache_key] = audio
    return audio


async def speech_to_text_async(
    audio_bytes: bytes,
    filename: str = "audio.wav",
    language_code: Optional[str] = "ta-IN",
    mode: Optional[str] = None,
    hotwords: Optional[list[str]] = None,
) -> str:
    result = await speech_to_text_result_async(audio_bytes, filename, language_code, mode, hotwords)
    return result.get("transcript", "")


async def speech_to_text_result_async(
    audio_bytes: bytes,
    filename: str = "audio.wav",
    language_code: Optional[str] = "ta-IN",
    mode: Optional[str] = None,
    hotwords: Optional[list[str]] = None,
) -> Dict[str, Any]:
    """Async Gemini STT. Returns transcript metadata."""
    _require_key()
    response = await _post_gemini_async("STT", STT_MODEL, _stt_payload(audio_bytes, language_code or "ta-IN"))
    raw = response.json()
    transcript = _extract_text(raw)
    print(f"[Gemini STT] transcript='{_safe_log_text(transcript[:80])}' confidence=None")
    return {"transcript": transcript, "confidence": None, "raw": raw}


def speech_to_text_result(
    audio_bytes: bytes,
    filename: str = "audio.wav",
    language_code: Optional[str] = "ta-IN",
    mode: Optional[str] = None,
    hotwords: Optional[list[str]] = None,
) -> Dict[str, Any]:
    _require_key()
    response = _post_gemini_sync("STT", STT_MODEL, _stt_payload(audio_bytes, language_code or "ta-IN"))
    raw = response.json()
    transcript = _extract_text(raw)
    print(f"[Gemini STT sync] transcript='{_safe_log_text(transcript[:80])}' confidence=None")
    return {"transcript": transcript, "confidence": None, "raw": raw}


def speech_to_text(
    audio_bytes: bytes,
    filename: str = "audio.wav",
    language_code: Optional[str] = "ta-IN",
    mode: Optional[str] = None,
    hotwords: Optional[list[str]] = None,
) -> str:
    return speech_to_text_result(audio_bytes, filename, language_code, mode, hotwords).get("transcript", "")


async def stream_speech_to_text_result_async(
    audio_chunks: AsyncIterable[bytes],
    language_code: Optional[str] = "ta-IN",
    on_transcript: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    mode: Optional[str] = None,
    hotwords: Optional[list[str]] = None,
) -> Dict[str, Any]:
    chunks = []
    async for chunk in audio_chunks:
        chunks.append(chunk)
    result = await speech_to_text_result_async(b"".join(chunks), language_code=language_code, mode=mode, hotwords=hotwords)
    if on_transcript and result.get("transcript"):
        await on_transcript(result)
    return result
