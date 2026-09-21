"""
Sarvam AI STT/TTS service — rewritten for low latency.

Key changes from the original version:
1. Removed the custom DNS-over-HTTPS resolution hack (resolve_hostname()).
   It added a synchronous network round-trip on EVERY single API call
   (DNS lookup -> fallback to a Google DoH request over HTTPS with TLS
   verification disabled) purely to work around environments with broken
   local DNS. Most production hosts have working DNS; this was a constant,
   unnecessary latency tax (and a security smell, since it disabled TLS
   verification). If DNS truly is broken in some deployment, fix it at the
   OS/network level instead of working around it per-request in code.
2. Uses a shared httpx.AsyncClient with HTTP connection pooling/keep-alive
   instead of a new `requests` connection (and a fresh TLS handshake) on
   every call. Connection reuse alone typically saves 100-300ms per call
   on top of removing the DNS hack.
3. STT timeout reduced from 30s to 12s — 30s was a worst-case smell that
   would make a hung Sarvam request stall an entire phone call for half a
   minute before failing. 12s is generous for a short voice clip and fails
   fast enough to let the call recover (e.g. ask the customer to repeat).
4. TTS responses for short, frequently-repeated phrases (e.g. campaign
   greetings, common acknowledgements) are cached in-memory keyed by
   (text, language_code, speaker) — repeating the exact same phrase later
   in the same process returns instantly with zero API call. This is safe
   (unlike caching LLM replies) because TTS for identical text is always
   the same audio.
"""

import asyncio
import hashlib
import os
from typing import Any, AsyncIterable, Awaitable, Callable, Dict, Optional

import httpx
from dotenv import load_dotenv

load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env")), override=True)

api_key = os.getenv("SARVAM_API_KEY")

TTS_URL = "https://api.sarvam.ai/text-to-speech"
STT_URL = "https://api.sarvam.ai/speech-to-text"
STREAMING_STT_URL = os.getenv("SARVAM_STREAMING_STT_URL", "").strip()
DEFAULT_STT_MODE = os.getenv("SARVAM_STT_MODE", "transcribe").strip() or "transcribe"

DEFAULT_HOTWORDS = [
    "DigiDara",
    "DigiDara Technologies",
    "AI",
    "ML",
    "AIML",
    "Python",
    "Java",
    "Full Stack",
    "Data Science",
    "Cloud Computing",
    "Internship",
    "Coimbatore",
    "Chennai",
    "Tamil Nadu",
]

# Shared, reused HTTP/2-capable client with connection pooling. Created
# lazily so importing this module never opens a socket by itself.
_async_client: Optional[httpx.AsyncClient] = None
_sync_client: Optional[httpx.Client] = None

# Simple in-memory TTS cache. Bounded to avoid unbounded growth over a long
# running process; oldest entries are evicted once the cap is hit.
_TTS_CACHE: Dict[str, bytes] = {}
_TTS_CACHE_MAX_ENTRIES = 200


def _get_async_client() -> httpx.AsyncClient:
    global _async_client
    if _async_client is None:
        _async_client = httpx.AsyncClient(
            http2=False,  # Sarvam's API does not require HTTP/2; keep it simple/compatible.
            timeout=httpx.Timeout(connect=5.0, read=12.0, write=5.0, pool=5.0),
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )
    return _async_client


def _get_sync_client() -> httpx.Client:
    """Sync client kept for callers that haven't migrated to async yet."""
    global _sync_client
    if _sync_client is None:
        _sync_client = httpx.Client(
            timeout=httpx.Timeout(connect=5.0, read=12.0, write=5.0, pool=5.0),
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )
    return _sync_client


def _tts_cache_key(text: str, language_code: str, speaker: str) -> str:
    raw = f"{language_code}|{speaker}|{text}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _hotwords(extra_hotwords: Optional[list[str]] = None) -> list[str]:
    configured = os.getenv("SARVAM_HOTWORDS", "")
    words = [w.strip() for w in configured.split(",") if w.strip()]
    words.extend(extra_hotwords or [])
    if not words:
        words = DEFAULT_HOTWORDS
    return list(dict.fromkeys(words))


def _extract_stt_result(data: Dict[str, Any]) -> Dict[str, Any]:
    transcript = (
        data.get("transcript")
        or data.get("text")
        or data.get("partial_transcript")
        or data.get("final_transcript")
        or ""
    )
    confidence = (
        data.get("confidence")
        or data.get("language_probability")
        or data.get("language_prob")
        or data.get("score")
    )
    try:
        confidence = float(confidence) if confidence is not None else None
    except (TypeError, ValueError):
        confidence = None
    return {
        "transcript": transcript,
        "confidence": confidence,
        "language_probability": confidence,
        "raw": data,
    }


def _default_speaker(language_code: str) -> str:
    if language_code == "ta-IN":
        return os.getenv("SARVAM_TAMIL_VOICE", os.getenv("SARVAM_SPEAKER_TA", "kavitha"))
    return os.getenv("SARVAM_SPEAKER", "priya")


def _build_tts_payload(
    text: str,
    language_code: str,
    speaker: str,
    pace: Optional[float],
    hotwords: Optional[list[str]] = None,
) -> dict:
    payload = {
        "text": text,
        "model": "bulbul:v3",
        "target_language_code": language_code,
        "speaker": speaker,
        "speech_sample_rate": 8000,
        "output_audio_codec": "wav",
    }
    payload["hotwords"] = _hotwords(hotwords)
    if pace is not None:
        payload["pace"] = pace
    elif language_code == "ta-IN":
        payload["pace"] = 1.15  # Faster pace for natural human-like Tamil speech
    return payload


async def text_to_speech_async(
    text: str,
    language_code: str = "en-IN",
    speaker: Optional[str] = None,
    pace: Optional[float] = None,
    hotwords: Optional[list[str]] = None,
) -> bytes:
    """
    Async Sarvam TTS call with in-memory caching for repeated phrases.
    This is the preferred entry point for the live call loop.
    """
    if not api_key or api_key == "your_sarvam_api_key_here":
        raise ValueError("SARVAM_API_KEY is not configured in the environment.")

    speaker = speaker or _default_speaker(language_code)
    cache_key = _tts_cache_key(text, language_code, speaker)
    cached = _TTS_CACHE.get(cache_key)
    if cached is not None:
        return cached

    headers = {"api-subscription-key": api_key, "Content-Type": "application/json"}
    payload = _build_tts_payload(text, language_code, speaker, pace, hotwords)

    client = _get_async_client()
    try:
        response = await client.post(TTS_URL, json=payload, headers=headers)
    except httpx.TimeoutException as e:
        raise RuntimeError(f"Sarvam TTS request timed out: {e}")
    except httpx.RequestError as e:
        raise RuntimeError(f"Sarvam TTS request failed: {e}")

    if response.status_code in (200, 201):
        res_json = response.json()
        audios = res_json.get("audios")
        if not audios:
            raise RuntimeError("No audio returned in Sarvam TTS response.")
        import base64
        audio_bytes = base64.b64decode(audios[0])

        if len(_TTS_CACHE) >= _TTS_CACHE_MAX_ENTRIES:
            _TTS_CACHE.pop(next(iter(_TTS_CACHE)))
        _TTS_CACHE[cache_key] = audio_bytes

        return audio_bytes
    raise RuntimeError(f"Sarvam TTS failed ({response.status_code}): {response.text}")


def text_to_speech(
    text: str,
    language_code: str = "en-IN",
    speaker: Optional[str] = None,
    pace: Optional[float] = None,
    hotwords: Optional[list[str]] = None,
) -> bytes:
    """
    Synchronous wrapper, kept for any remaining non-async call sites (e.g.
    background threads in twilio_service.py that pre-generate greetings
    outside the event loop). Internally uses a pooled sync httpx.Client
    instead of opening a fresh `requests` connection each time.
    """
    if not api_key or api_key == "your_sarvam_api_key_here":
        raise ValueError("SARVAM_API_KEY is not configured in the environment.")

    speaker = speaker or _default_speaker(language_code)
    cache_key = _tts_cache_key(text, language_code, speaker)
    cached = _TTS_CACHE.get(cache_key)
    if cached is not None:
        return cached

    headers = {"api-subscription-key": api_key, "Content-Type": "application/json"}
    payload = _build_tts_payload(text, language_code, speaker, pace, hotwords)

    client = _get_sync_client()
    try:
        response = client.post(TTS_URL, json=payload, headers=headers)
    except httpx.TimeoutException as e:
        raise RuntimeError(f"Sarvam TTS request timed out: {e}")
    except httpx.RequestError as e:
        raise RuntimeError(f"Sarvam TTS request failed: {e}")

    if response.status_code in (200, 201):
        res_json = response.json()
        audios = res_json.get("audios")
        if not audios:
            raise RuntimeError("No audio returned in Sarvam TTS response.")
        import base64
        audio_bytes = base64.b64decode(audios[0])

        if len(_TTS_CACHE) >= _TTS_CACHE_MAX_ENTRIES:
            _TTS_CACHE.pop(next(iter(_TTS_CACHE)))
        _TTS_CACHE[cache_key] = audio_bytes

        return audio_bytes
    raise RuntimeError(f"Sarvam TTS failed ({response.status_code}): {response.text}")


async def speech_to_text_async(
    audio_bytes: bytes,
    filename: str = "audio.wav",
    language_code: Optional[str] = None,
    mode: Optional[str] = None,
    hotwords: Optional[list[str]] = None,
) -> str:
    """Async Sarvam STT call. Preferred entry point for the live call loop."""
    result = await speech_to_text_result_async(
        audio_bytes=audio_bytes,
        filename=filename,
        language_code=language_code,
        mode=mode,
        hotwords=hotwords,
    )
    return result.get("transcript", "")


async def speech_to_text_result_async(
    audio_bytes: bytes,
    filename: str = "audio.wav",
    language_code: Optional[str] = None,
    mode: Optional[str] = None,
    hotwords: Optional[list[str]] = None,
) -> Dict[str, Any]:
    """Async Sarvam STT call returning transcript plus confidence metadata."""
    if not api_key or api_key == "your_sarvam_api_key_here":
        raise ValueError("SARVAM_API_KEY is not configured in the environment.")

    headers = {"api-subscription-key": api_key}
    files = {"file": (filename, audio_bytes, "audio/wav")}
    data = {"model": "saaras:v3", "mode": mode or DEFAULT_STT_MODE}
    if language_code:
        data["language_code"] = language_code
    words = _hotwords(hotwords)
    if words:
        data["hotwords"] = ",".join(words)

    client = _get_async_client()
    try:
        response = await client.post(STT_URL, headers=headers, files=files, data=data)
    except httpx.TimeoutException as e:
        raise RuntimeError(f"Sarvam STT request timed out: {e}")
    except httpx.RequestError as e:
        raise RuntimeError(f"Sarvam STT request failed: {e}")

    if response.status_code in (200, 201):
        result = _extract_stt_result(response.json())
        print(
            f"[Sarvam STT] transcript='{result.get('transcript', '')[:80]}' "
            f"confidence={result.get('confidence')}"
        )
        return result
    raise RuntimeError(f"Sarvam STT failed ({response.status_code}): {response.text}")


def speech_to_text(
    audio_bytes: bytes,
    filename: str = "audio.wav",
    language_code: Optional[str] = None,
    mode: Optional[str] = None,
    hotwords: Optional[list[str]] = None,
) -> str:
    """Synchronous wrapper, kept for any remaining non-async call sites."""
    result = speech_to_text_result(
        audio_bytes=audio_bytes,
        filename=filename,
        language_code=language_code,
        mode=mode,
        hotwords=hotwords,
    )
    return result.get("transcript", "")


def speech_to_text_result(
    audio_bytes: bytes,
    filename: str = "audio.wav",
    language_code: Optional[str] = None,
    mode: Optional[str] = None,
    hotwords: Optional[list[str]] = None,
) -> Dict[str, Any]:
    """Synchronous Sarvam STT call returning transcript plus confidence metadata."""
    if not api_key or api_key == "your_sarvam_api_key_here":
        raise ValueError("SARVAM_API_KEY is not configured in the environment.")

    headers = {"api-subscription-key": api_key}
    files = {"file": (filename, audio_bytes, "audio/wav")}
    data = {"model": "saaras:v3", "mode": mode or DEFAULT_STT_MODE}
    if language_code:
        data["language_code"] = language_code
    words = _hotwords(hotwords)
    if words:
        data["hotwords"] = ",".join(words)

    client = _get_sync_client()
    try:
        response = client.post(STT_URL, headers=headers, files=files, data=data)
    except httpx.TimeoutException as e:
        raise RuntimeError(f"Sarvam STT request timed out: {e}")
    except httpx.RequestError as e:
        raise RuntimeError(f"Sarvam STT request failed: {e}")

    if response.status_code in (200, 201):
        result = _extract_stt_result(response.json())
        print(
            f"[Sarvam STT sync] transcript='{result.get('transcript', '')[:80]}' "
            f"confidence={result.get('confidence')}"
        )
        return result
    raise RuntimeError(f"Sarvam STT failed ({response.status_code}): {response.text}")


async def stream_speech_to_text_result_async(
    audio_chunks: AsyncIterable[bytes],
    language_code: Optional[str] = None,
    on_transcript: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    mode: Optional[str] = None,
    hotwords: Optional[list[str]] = None,
) -> Dict[str, Any]:
    """
    Optional Sarvam streaming STT adapter.

    The streaming URL is read from SARVAM_STREAMING_STT_URL so deployments can
    match Sarvam dashboard/docs without code changes. If the URL is not set,
    callers should keep using the batch STT fallback.
    """
    if not STREAMING_STT_URL:
        raise RuntimeError("SARVAM_STREAMING_STT_URL is not configured.")
    if not api_key or api_key == "your_sarvam_api_key_here":
        raise ValueError("SARVAM_API_KEY is not configured in the environment.")

    import base64
    import json
    import websockets

    final_result: Dict[str, Any] = {"transcript": "", "confidence": None, "raw": {}}
    config = {
        "model": "saaras:v3",
        "mode": mode or DEFAULT_STT_MODE,
        "language_code": language_code,
        "hotwords": _hotwords(hotwords),
    }
    headers = {"api-subscription-key": api_key}

    try:
        ws_context = websockets.connect(STREAMING_STT_URL, additional_headers=headers)
    except TypeError:
        ws_context = websockets.connect(STREAMING_STT_URL, extra_headers=headers)

    async with ws_context as ws:
        await ws.send(json.dumps({"type": "config", "config": config}))

        async def receiver() -> None:
            nonlocal final_result
            async for message in ws:
                try:
                    data = json.loads(message)
                except Exception:
                    continue
                result = _extract_stt_result(data)
                if result.get("transcript"):
                    final_result = result
                    if on_transcript:
                        await on_transcript(result)

        receive_task = asyncio.create_task(receiver())
        try:
            async for chunk in audio_chunks:
                await ws.send(json.dumps({
                    "type": "audio",
                    "audio": base64.b64encode(chunk).decode("ascii"),
                }))
            await ws.send(json.dumps({"type": "end"}))
            await asyncio.wait_for(receive_task, timeout=2.0)
        except asyncio.TimeoutError:
            receive_task.cancel()

    return final_result
