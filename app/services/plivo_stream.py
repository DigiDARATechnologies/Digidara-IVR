"""Pure Plivo Audio Streaming protocol helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from html import escape
from typing import Any


def parse_start(event: dict[str, Any]) -> tuple[str | None, str | None]:
    start = event.get("start") or {}
    return start.get("callId") or start.get("callUuid"), start.get("streamId")


def media_payload(event: dict[str, Any]) -> str | None:
    return (event.get("media") or {}).get("payload")


def play_audio(payload: str) -> dict[str, Any]:
    # OpenAI Realtime emits base64 G.711 mu-law at 8 kHz already.
    base64.b64decode(payload, validate=True)
    return {
        "event": "playAudio",
        "media": {
            "contentType": "audio/x-mulaw",
            "sampleRate": 8000,
            "payload": payload,
        },
    }


def checkpoint(stream_id: str, name: str) -> dict[str, Any]:
    return {"event": "checkpoint", "streamId": stream_id, "name": name}


def clear_audio(stream_id: str) -> dict[str, str]:
    return {"event": "clearAudio", "streamId": stream_id}


def _stream_body_xml(
    stream_url: str,
    recording_callback_url: str,
    stream_status_url: str,
    recording_max_length_seconds: int = 14400,
) -> str:
    safe_max_length = max(60, min(int(recording_max_length_seconds), 14400))
    return f"""<Record recordSession="true" recordChannelType="stereo" fileFormat="mp3"
          maxLength="{safe_max_length}" playBeep="false"
          callbackUrl="{escape(recording_callback_url, quote=True)}" callbackMethod="POST" />
  <Stream keepCallAlive="true" bidirectional="true" audioTrack="inbound"
          contentType="audio/x-mulaw;rate=8000"
          statusCallbackUrl="{escape(stream_status_url, quote=True)}" statusCallbackMethod="POST">{escape(stream_url, quote=False)}</Stream>"""


def build_answer_xml(
    stream_url: str,
    recording_callback_url: str,
    stream_status_url: str,
    recording_max_length_seconds: int = 14400,
) -> str:
    """Build the single-voice Plivo answer document without carrier speech."""
    body = _stream_body_xml(
        stream_url, recording_callback_url, stream_status_url, recording_max_length_seconds
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  {body}
</Response>"""


def build_language_prompt_xml(
    action_url: str,
    play_url: str,
    stream_url: str,
    recording_callback_url: str,
    stream_status_url: str,
    recording_max_length_seconds: int = 14400,
    timeout_seconds: int = 6,
) -> str:
    """Ask the customer to pick English/Tamil by DTMF before the AI stream starts.

    Plivo's own <Speak> engine can't render Tamil script, so the menu is a
    pre-rendered clip played via <Play> instead of native TTS. If no valid
    digit arrives within the timeout, Plivo falls through to the same
    Record/Stream verbs used by build_answer_xml, so the call still connects
    (in whatever language the customer record already has) instead of
    stalling on a keypress that never comes.
    """
    body = _stream_body_xml(
        stream_url, recording_callback_url, stream_status_url, recording_max_length_seconds
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <GetDigits action="{escape(action_url, quote=True)}" method="POST"
             timeout="{max(3, int(timeout_seconds))}" numDigits="1" retries="1">
    <Play>{escape(play_url, quote=False)}</Play>
  </GetDigits>
  {body}
</Response>"""


def build_direct_dial_xml(
    action_url: str, confirm_sound_url: str, destination_phone: str | list[str],
    dial_timeout_seconds: int = 25,
) -> str:
    """Ring one or more human destinations directly (simultaneous hunt group)
    with no AI leg at all, for an IVR option or transfer that routes to staff.

    confirmKey="1" makes Plivo require the person who picks up to press 1
    before bridging the caller in, so a voicemail pickup or wrong number
    doesn't silently swallow the call. When multiple numbers are specified,
    Plivo dials all in parallel; the first to confirm wins and others are cancelled.
    """
    phones = [destination_phone] if isinstance(destination_phone, str) else [p for p in destination_phone if p]
    if not phones:
        phones = [""]
    number_tags = "\n".join(f"    <Number>{escape(p, quote=False)}</Number>" for p in phones)
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Dial action="{escape(action_url, quote=True)}" method="POST"
        timeout="{max(10, min(int(dial_timeout_seconds), 45))}" timeLimit="14400"
        confirmSound="{escape(confirm_sound_url, quote=True)}" confirmKey="1" confirmTimeout="10">
{number_tags}
  </Dial>
</Response>'''


def build_ivr_prompt_xml(
    action_url: str, play_url: str, stream_url: str,
    recording_callback_url: str, stream_status_url: str,
    recording_max_length_seconds: int = 14400, timeout_seconds: int = 7,
    speech_hints: str = "", language_code: str = "en-US",
) -> str:
    """Collect a tenant IVR selection by digit OR spoken word, then safely
    fall through to the AI stream if neither arrives in time.

    <GetInput inputType="dtmf speech"> accepts both simultaneously, so a
    caller can either press the option's number or just say its name — the
    action webhook receives whichever one the caller actually used (Digits
    or SpeechResult). hints biases Plivo's speech recognizer toward the
    tenant's exact configured department names for better accuracy.
    """
    body = _stream_body_xml(
        stream_url, recording_callback_url, stream_status_url, recording_max_length_seconds
    )
    execution_timeout = max(3, min(int(timeout_seconds), 15))
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <GetInput action="{escape(action_url, quote=True)}" method="POST"
            inputType="dtmf speech" numDigits="1"
            executionTimeout="{execution_timeout}" digitEndTimeout="2" speechEndTimeout="2"
            language="{escape(language_code, quote=True)}"
            hints="{escape(speech_hints, quote=True)}">
    <Play>{escape(play_url, quote=False)}</Play>
  </GetInput>
  {body}
</Response>'''


import time


def _stream_secret() -> bytes:
    value = (
        os.getenv("PLIVO_STREAM_TOKEN_SECRET")
        or os.getenv("PLIVO_AUTH_TOKEN")
        or os.getenv("JWT_SECRET")
        or ""
    )
    return value.encode("utf-8")


def stream_token(
    customer_id: int,
    campaign_id: int,
    correlation_id: str,
    timestamp: int | None = None,
) -> str:
    """Generate a tamper-proof stream token bound to a timestamp."""
    ts = int(timestamp if timestamp is not None else time.time())
    message = f"{customer_id}:{campaign_id}:{correlation_id}:{ts}".encode("utf-8")
    sig = hmac.new(_stream_secret(), message, hashlib.sha256).hexdigest()
    return f"{sig}.{ts}"


def validate_stream_token(
    token: str,
    customer_id: int,
    campaign_id: int,
    correlation_id: str,
    max_age_seconds: int = 1800,
) -> bool:
    """Validate token integrity, signature, and expiration window (default 30 mins)."""
    if not token or not _stream_secret():
        return False

    secret = _stream_secret()

    # Case 1: Timestamped token format: <signature>.<timestamp>
    if "." in token:
        parts = token.split(".", 1)
        if len(parts) != 2:
            return False
        sig, ts_str = parts
        try:
            ts = int(ts_str)
        except ValueError:
            return False

        # Expiration check
        now = int(time.time())
        if ts > now + 300 or (now - ts) > max_age_seconds:
            return False

        expected_message = f"{customer_id}:{campaign_id}:{correlation_id}:{ts}".encode("utf-8")
        expected_sig = hmac.new(secret, expected_message, hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected_sig)

    # Case 2: Legacy fallback token (un-timestamped) for backward compatibility
    legacy_message = f"{customer_id}:{campaign_id}:{correlation_id}".encode("utf-8")
    legacy_sig = hmac.new(secret, legacy_message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(token, legacy_sig)


def websocket_signature_url(base: str, path: str, query: str) -> str:
    """Return the HTTP upgrade URL Plivo signs for a WSS destination."""
    http_base = base.strip().rstrip("/")
    if http_base.startswith("wss://"):
        http_base = "https://" + http_base[len("wss://"):]
    elif http_base.startswith("ws://"):
        http_base = "http://" + http_base[len("ws://"):]
    suffix = f"?{query}" if query else ""
    return f"{http_base}{path}{suffix}"
