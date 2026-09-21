"""Plivo Audio Streaming bridge for OpenAI GPT-Realtime.

Both English and Tamil calls use the same native audio-to-audio session. Plivo
sends and receives 8 kHz G.711 mu-law, so no WAV files or transcoding are needed.
"""

import asyncio
import base64
import hashlib
import json
import os
import re
import time
from collections import deque
from typing import Any, Optional
from urllib.parse import urlencode

import websockets
from dotenv import load_dotenv
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.database.db import get_db_connection
from app.services import call_log_service, campaign_service, ivr_service, memory_service, transfer_service
from app.services.conversation_service import save_conversation
from app.services.audio_utils import MuLawSpeechEnhancer
from app.services.call_inactivity import (
    CallInactivityPolicy,
    inactivity_goodbye_instruction,
    inactivity_reprompt_instruction,
)
from app.services.realtime_turns import (
    DEFAULT_PLAYBACK_MARK_INTERVAL_MS,
    PCMU_BYTES_PER_MILLISECOND,
    bounded_float_env,
    bounded_int_env,
    parse_playback_mark,
    playback_mark_name,
)
from app.services.realtime_input_gate import (
    TurnAudioStats,
    build_turn_stats,
    caller_perceived_latency_ms,
    is_credible_barge_in,
    mulaw_rms,
    validate_turn,
)
from app.services.plivo_stream import (
    checkpoint,
    clear_audio,
    media_payload,
    parse_start,
    play_audio,
    validate_stream_token,
    websocket_signature_url,
)
from app.services.telephony import get_telephony_provider
from app.services.tenant_credentials_service import resolve_openai_api_key
from app.services.usage_cost_service import (
    COST_ESTIMATION_VERSION,
    estimate_openai_cost_usd,
)
from app.services.conversation_policy_service import (
    CONVERSATION_POLICY_PROFILE,
    ENGLISH_STYLE_PROFILE,
    KNOWLEDGE_PROFILE,
    TAMIL_STYLE_PROFILE,
    build_existing_english_session_instructions,
    build_greeting_instruction,
    build_inbound_greeting_instruction,
    build_router_greeting_instruction,
    build_initial_session_instructions,
    build_response_instruction,
    classify_intent,
    count_response_sentences,
    count_response_words,
    is_do_not_call_intent,
    is_end_call_intent,
    is_not_interested_intent,
    is_stop_intent,
    resolve_realtime_model,
    resolve_realtime_voice,
)
from app.utils.token_estimator import estimate_prompt_tokens


router = APIRouter(tags=["OpenAI Realtime Voice"])

def _instructions(
    language: str, customer: dict, campaign: dict | None, memory: Any,
    organization_name: str = "DigiDara Technologies",
) -> str:
    """Build the session-level system prompt for the generic AI receptionist."""
    if language == "tamil":
        return build_initial_session_instructions(
            language, customer, campaign, memory, organization_name=organization_name,
        )
    return build_existing_english_session_instructions(
        customer, campaign, memory, organization_name=organization_name,
    )


def _router_instructions(language: str, menu: dict[str, Any], organization_name: str) -> str:
    """Build the short-lived system prompt used only for the first turn of a
    call whose organization has an active IVR menu: greet, ask which
    department the caller needs, then silently call route_to_human. This
    intentionally replaces the full campaign script until routing happens.
    """
    labels = [str(item["label"]) for item in menu.get("options", [])]
    choices = ", ".join(labels)
    prompt = str(menu.get("prompt") or "").strip()
    question = prompt or f"What do you need help with today — {choices}?"
    if language == "tamil":
        return (
            f"நீங்கள் {organization_name} நிறுவனத்தின் AI voice assistant. "
            f"முதலில் சுருக்கமா வணக்கம் சொல்லி நீங்க யாருனு தெரிவிங்க, பிறகு இந்த கேள்வியை "
            f"கேளுங்க: \"{question}\". Customer பதில் சொன்ன உடனே, அவங்க கேட்ட department-ஐ "
            f"({choices} இதில் ஒண்ணு) புரிஞ்சுக்கிட்டு, பேசாம route_to_human tool-ஐ silent-ஆ "
            f"call பண்ணுங்க. பதில் தெளிவா இல்லைனா, ஒரு தடவை மட்டும் மறுபடியும் தெளிவா கேளுங்க. "
            f"இந்த கேள்விக்கு அப்புறம் வேற எந்த topic பத்தியும் பேச வேண்டாம்."
        )
    return (
        f"You are the AI voice assistant for {organization_name}. Greet the caller briefly, "
        f"introduce yourself in one short sentence, then ask exactly this (or very close to "
        f"it): \"{question}\" As soon as the caller states which one they need, silently call "
        f"the route_to_human tool with that department -- do not start a longer conversation "
        f"about their need first, and do not answer questions about it yourself. Valid options: "
        f"{choices}. If their answer is unclear or doesn't match any option, ask once more for "
        f"clarification before calling the tool. If the caller asks something unrelated to "
        f"{organization_name}'s business instead of answering the question, say once, briefly, "
        f"that you can't answer that, then ask the routing question again."
    )


def _end_call_tool_definition() -> dict[str, Any]:
    return {
        "type": "function",
        "name": "end_call",
        "description": (
            "Call this the moment it is clear, in any wording, tone, "
            "or language, that the customer wants this phone call to "
            "stop now. This includes explicit goodbyes, asking you to "
            "hang up/cut/disconnect the call, saying they are not "
            "interested, asking you to stop calling them, or any other "
            "way of indicating the conversation should end -- including "
            "phrasing you have not heard before. Trust your judgment of "
            "the customer's intent rather than matching exact words. Do "
            "not call this just because they said thank you, asked a "
            "normal question, or are still engaged in the conversation. "
            "Never call this for unclear, partial or unintelligible "
            "speech, silence, noise, or a request to repeat or clarify; "
            "ask one short clarification and keep the call open. "
            "Call this tool silently, without speaking, in the same turn "
            "you decide to end the call -- you will be given a separate "
            "turn immediately after to say a brief goodbye."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "enum": [
                        "customer_goodbye",
                        "customer_not_interested",
                        "customer_do_not_call",
                        "other",
                    ],
                    "description": (
                        "customer_do_not_call only if the customer "
                        "explicitly asked to not be called again or to "
                        "be removed from the list."
                    ),
                },
            },
            "required": ["reason"],
        },
    }


def _transfer_to_human_tool_definition() -> dict[str, Any]:
    return {
        "type": "function",
        "name": "transfer_to_human",
        "description": (
            "Call this the moment the customer clearly asks to speak with a "
            "human, a real person, a counsellor, or an agent, or asks you to "
            "connect/transfer them to someone -- do not just say you will "
            "connect them, you must actually call this tool. Call it "
            "silently, without speaking first -- you will get one more turn "
            "immediately after to tell them you're connecting them."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    }


def _route_to_human_tool_definition(labels: list[str]) -> dict[str, Any]:
    return {
        "type": "function",
        "name": "route_to_human",
        "description": (
            "Call this the moment the caller has told you which department "
            "they need. Pass the department exactly as one of the listed "
            "options. Call this silently, without speaking first -- you "
            "will get one more turn immediately after to tell the caller "
            "you're connecting them."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "department": {"type": "string", "enum": labels},
            },
            "required": ["department"],
        },
    }


def _greeting_instruction(
    operator: dict, language: str, organization_name: str = "DigiDara Technologies",
    call_direction: str = "outbound",
) -> str:
    """Create the single system-owned opening response."""
    if call_direction == "inbound":
        return build_inbound_greeting_instruction(language, organization_name=organization_name)
    return build_greeting_instruction(language, operator, organization_name=organization_name)


def _validated_turn_instruction(
    transcript: str, language: str, previous_answer: str,
    knowledge_chunks: list | None = None, ending: bool = False,
) -> str:
    del ending  # build_response_instruction classifies end-call intent from transcript itself
    return build_response_instruction(
        language, transcript, knowledge_chunks=knowledge_chunks or [], previous_answer=previous_answer,
    )


def _clean_env_value(name: str, default: str = "") -> str:
    """Protect model/voice values copied with accidental inline comments."""
    return (os.getenv(name, default) or default).split("#", 1)[0].strip()


def resolve_vad_eagerness(language: str) -> str:
    """Resolve a supported semantic-VAD profile for the selected language."""
    is_tamil = language == "tamil"
    default = "high" if is_tamil else "medium"
    value = _clean_env_value(
        "OPENAI_VAD_EAGERNESS_TAMIL" if is_tamil
        else "OPENAI_VAD_EAGERNESS_ENGLISH",
        default,
    ).lower()
    return value if value in {"low", "medium", "high", "auto"} else default


def build_turn_detection_config(language: str) -> dict:
    """Use bounded silence for English and validated semantic turns for Tamil."""
    automatic_response = language == "english"
    common = {
        "create_response": automatic_response,
        "interrupt_response": automatic_response,
    }
    if language == "tamil":
        return {
            "type": "semantic_vad",
            "eagerness": resolve_vad_eagerness(language),
            **common,
        }
    return {
        "type": "server_vad",
        # Phone-line audio (especially the assistant's own TTS bleeding back
        # into the caller's mic) can false-trigger a lower threshold as a new
        # customer turn, cancelling the in-progress response and forcing a
        # regeneration — call-50's transcript showed the mini model losing
        # its thread and re-introducing itself after several of these.
        # Raised the default from 0.5 to reduce that without raising it so
        # far it starts missing real, quieter interruptions.
        "threshold": bounded_float_env(
            "OPENAI_SERVER_VAD_THRESHOLD_ENGLISH", 0.6, 0.3, 0.9
        ),
        "prefix_padding_ms": 300,
        "silence_duration_ms": bounded_int_env(
            "OPENAI_SERVER_VAD_SILENCE_MS_ENGLISH", 650, 400, 1500
        ),
        **common,
    }


def _input_transcription_config(
    language: str, transcription_model: str, customer: dict,
) -> dict:
    """Build ASR guidance; Tamil is intentionally auto-detected for Tanglish."""
    config = {"model": transcription_model}
    if language != "tamil":
        config["language"] = "en"
        return config

    language_hint = _clean_env_value("OPENAI_TRANSCRIPTION_LANGUAGE_TAMIL")
    if language_hint:
        config["language"] = language_hint
    config["prompt"] = _clean_env_value(
        "OPENAI_TRANSCRIPTION_PROMPT_TAMIL",
        (
            "இது தமிழ்நாட்டு கல்வி enquiry phone call. இயல்பான பேச்சுத் தமிழ், "
            "Tamil Tanglish மற்றும் English technical words-ஐ பேசியபடியே எழுதவும். "
            "Common terms: facility, maintenance, asset, AHU, chiller, HVAC, airflow, "
            "sensor, energy, alert, work order, service request, Building A."
        ),
    )
    return config


@router.websocket("/ws/plivo/media")
async def openai_realtime(
    websocket: WebSocket, customer_id: int, campaign_id: int,
    correlation_id: str, token: str,
):
    if not validate_stream_token(token, customer_id, campaign_id, correlation_id):
        await websocket.close(code=1008, reason="Invalid stream token")
        return

    # The HMAC token is created only after the signed Plivo answer callback.
    # Also bind it to a recent, active database row so a leaked/replayed URL
    # cannot create an unrelated media session.
    auth_db = get_db_connection()
    try:
        auth_cursor = auth_db.cursor()
        auth_cursor.execute(
            """SELECT id,organization_id,call_direction FROM call_logs
               WHERE correlation_id=%s AND customer_id=%s AND campaign_id=%s
                 AND provider='plivo'
                 AND COALESCE(call_status,status) IN
                     ('queued','initiated','ringing','in-progress')
                 AND created_at >= NOW() - INTERVAL 30 MINUTE
               ORDER BY id DESC LIMIT 1""",
            (correlation_id, customer_id, campaign_id),
        )
        auth_row = auth_cursor.fetchone()
        valid_context = bool(auth_row)
        call_organization_id = auth_row.get("organization_id") if auth_row else None
        call_log_id = int(auth_row["id"]) if auth_row else None
        call_direction = str((auth_row.get("call_direction") if auth_row else None) or "outbound")
    finally:
        auth_db.close()
    if not valid_context:
        await websocket.close(code=1008, reason="Invalid or expired stream context")
        return

    # Plivo's HTTP callbacks always use V3 validation. WebSocket upgrades pass
    # through reverse proxies (Cloudflare in local testing), where the URL
    # scheme/host canonicalization can differ from Plivo's signed value. The
    # signed-answer -> HMAC-token -> active-context chain above is the primary
    # WebSocket authentication. Strict V3 validation remains opt-in for
    # deployments whose proxy preserves the exact signed upgrade URL.
    validate_websocket_signature = (
        os.getenv("PLIVO_VALIDATE_WEBSOCKET_SIGNATURES") or "false"
    ).lower() in {
        "1", "true", "yes", "on",
    }
    if validate_websocket_signature:
        base = (os.getenv("PLIVO_STREAM_BASE_URL") or "").strip().rstrip("/")
        signed_url = (
            websocket_signature_url(
                base, websocket.url.path, websocket.url.query
            )
            if base else str(websocket.url)
        )
        signature_db = get_db_connection()
        try:
            signature_provider = get_telephony_provider(signature_db, call_organization_id)
        finally:
            signature_db.close()
        valid_provider = signature_provider.validate_callback(
            method="GET",
            url=signed_url,
            nonce=websocket.headers.get("X-Plivo-Signature-V3-Nonce", ""),
            signature=websocket.headers.get("X-Plivo-Signature-V3", ""),
            params=dict(websocket.query_params),
        )
        if not valid_provider:
            await websocket.close(code=1008, reason="Invalid Plivo V3 signature")
            return
    await websocket.accept()
    db = get_db_connection()
    cursor = db.cursor()
    api_key = (resolve_openai_api_key(db, call_organization_id) or "").strip()
    if not api_key:
        print("[OpenAI Realtime][CONFIG ERROR] OPENAI_API_KEY is missing")
        await websocket.close(code=1011, reason="OPENAI_API_KEY is not configured")
        db.close()
        return
    cursor.execute(
        "SELECT name, phone, organization_id, language FROM customers WHERE id=%s",
        (customer_id,),
    )
    operator = cursor.fetchone() or {}
    # The signed Plivo contract still names this identifier ``customer_id``.
    # Keep a local compatibility alias for call logging and suppression checks.
    customer = operator
    language = (operator.get("language") or "english").strip().lower()
    language = "tamil" if language == "tamil" else "english"
    try:
        model = resolve_realtime_model(language)
        voice, voice_type, voice_label = resolve_realtime_voice(language)
    except RuntimeError as exc:
        print(f"[OpenAI Realtime][CONFIG ERROR] {exc}")
        db.close()
        await websocket.close(code=1011, reason="Realtime model or voice is not configured")
        return
    transcription_model = _clean_env_value(
        "OPENAI_TRANSCRIPTION_MODEL_TAMIL" if language == "tamil"
        else "OPENAI_TRANSCRIPTION_MODEL",
        "gpt-4o-transcribe" if language == "tamil" else "gpt-4o-mini-transcribe",
    )
    transcription_config = _input_transcription_config(
        language, transcription_model, operator,
    )
    voice_style_profile = TAMIL_STYLE_PROFILE if language == "tamil" else ENGLISH_STYLE_PROFILE
    knowledge_profile = KNOWLEDGE_PROFILE
    conversation_profile = CONVERSATION_POLICY_PROFILE
    turn_gate_profile = (
        "validated_tamil_turns_v1"
        if language == "tamil" else "openai_server_vad_english_v1"
    )
    if not operator.get("organization_id"):
        db.close()
        await websocket.close(code=1008, reason="Customer context is unavailable")
        return
    organization_id = int(operator["organization_id"])
    cursor.execute("SELECT name FROM organizations WHERE id=%s", (organization_id,))
    organization_name = (cursor.fetchone() or {}).get("name") or "DigiDara Technologies"
    campaign = campaign_service.get_campaign_by_id(db, campaign_id, organization_id)
    memory = memory_service.get_memory(db, customer_id)

    # An organization with an active IVR menu routes the call by AI-driven
    # conversation instead of the campaign's full script: greet, ask which
    # department the caller needs, then hand off (human transfer or a
    # session.update into that department's own campaign). Skipped once a
    # selection already exists for this call, so a mid-call reconnect (or
    # the AI-routed switch below) never re-asks the question.
    ivr_menu = ivr_service.get_live_menu(db, organization_id, language)
    already_routed = False
    if ivr_menu and call_log_id:
        cursor.execute(
            "SELECT 1 FROM call_ivr_selections WHERE call_log_id=%s", (call_log_id,),
        )
        already_routed = bool(cursor.fetchone())
    router_mode = bool(ivr_menu and not already_routed)

    if router_mode:
        instructions = _router_instructions(language, ivr_menu, organization_name)
    else:
        instructions = _instructions(language, operator, campaign, memory, organization_name)
    prompt_metrics = {
        "profile": CONVERSATION_POLICY_PROFILE,
        "total_estimated_tokens": estimate_prompt_tokens(instructions),
        "knowledge_estimated_tokens": 0,
    }
    max_initial_prompt_tokens = bounded_int_env(
        "INITIAL_PROMPT_MAX_ESTIMATED_TOKENS", 1200, 600, 3000
    )
    print(
        "[OpenAI Realtime] prompt metrics | "
        f"profile={conversation_profile} language={language} "
        "legacy_campaign_estimate=0 "
        "compacted_campaign_estimate=0 "
        f"initial_estimate={prompt_metrics.get('total_estimated_tokens', 0)} "
        f"budget={max_initial_prompt_tokens}"
    )
    enhancement_setting = _clean_env_value(
        "INBOUND_AUDIO_ENHANCEMENT_TAMIL" if language == "tamil"
        else "INBOUND_AUDIO_ENHANCEMENT",
        "false" if language == "tamil" else "true",
    )
    enhance_input = enhancement_setting.lower() in {"1", "true", "yes", "on"}
    input_enhancer = MuLawSpeechEnhancer(
        target_rms=float(_clean_env_value("INBOUND_TARGET_RMS", "2200")),
        max_gain=float(_clean_env_value("INBOUND_MAX_GAIN", "2.8")),
        noise_gate_rms=float(_clean_env_value("INBOUND_NOISE_GATE_RMS", "170")),
    )
    stream_sid: Optional[str] = None
    call_sid: Optional[str] = None
    started_at = time.monotonic()
    first_audio_at: Optional[float] = None
    response_latency_started_at: Optional[float] = None
    turn_latencies: list[int] = []
    transcript_lines: list[str] = []
    usage_totals = {
        "input_audio": 0,
        "output_audio": 0,
        "input_text": 0,
        "output_text": 0,
        "cached_input_audio": 0,
        "cached_input_text": 0,
        "total": 0,
        "transcription_input_audio": 0,
        "transcription_output_text": 0,
    }
    current_response_id: Optional[str] = None
    response_item_id: Optional[str] = None
    greeting_requested = False
    response_audio_sent_bytes = 0
    response_audio_played_ms = 0
    response_last_mark_ms = 0
    interruption_count = 0
    false_turn_count = 0
    interrupted_item_ids: set[str] = set()
    interrupted_response_ids: set[str] = set()
    cancel_sent_response_ids: set[str] = set()
    suppress_response_audio = False
    response_in_progress = False
    recent_assistant_text = ""
    assistant_transcript_parts: list[str] = []
    recent_input_rms: deque[float] = deque(maxlen=15)
    latest_voiced_frame_at: Optional[float] = None
    active_input_item_id: Optional[str] = None
    turn_started_at: dict[str, float] = {}
    turn_audio_start_ms: dict[str, int] = {}
    turn_rms_frames: dict[str, list[float]] = {}
    turn_last_voiced_at: dict[str, float] = {}
    barge_in_rms_frames: dict[str, list[float]] = {}
    provisional_interrupted_items: set[str] = set()
    turn_stats: dict[str, TurnAudioStats] = {}
    pending_transcripts: dict[str, tuple[str, Optional[str]]] = {}
    validated_transcripts: dict[str, str] = {}
    processed_input_items: set[str] = set()
    pending_response_items: deque[str] = deque()
    response_lock = asyncio.Lock()
    latest_customer_turn_id = 0
    response_language = language
    turn_sequence_by_item: dict[str, int] = {}
    latest_intent = "greeting"
    stop_intent_count = 0
    callback_intent_count = 0
    end_call_intent_count = 0
    cancelled_response_count = 0
    assistant_response_word_counts: list[int] = []
    assistant_response_sentence_counts: list[int] = []
    shared_target_response_words = bounded_int_env(
        "TARGET_RESPONSE_WORDS_MAX", 30, 12, 80
    )
    target_response_words_max = bounded_int_env(
        "TARGET_RESPONSE_WORDS_MAX_ENGLISH" if language == "english"
        else "TARGET_RESPONSE_WORDS_MAX_TAMIL",
        20 if language == "english" else shared_target_response_words,
        12,
        80,
    )
    max_response_sentences = bounded_int_env(
        "MAX_RESPONSE_SENTENCES", 2, 1, 4
    )
    env_prefix = "TAMIL" if language == "tamil" else "ENGLISH"
    turn_voiced_rms = float(_clean_env_value(f"{env_prefix}_TURN_VOICED_RMS", "220"))
    turn_min_peak_rms = float(_clean_env_value(f"{env_prefix}_TURN_MIN_PEAK_RMS", "240"))
    turn_min_duration_ms = bounded_int_env(
        f"{env_prefix}_TURN_MIN_DURATION_MS",
        240 if language == "tamil" else 160,
        120,
        1200,
    )
    turn_min_voiced_frames = bounded_int_env(
        f"{env_prefix}_TURN_MIN_VOICED_FRAMES",
        3 if language == "tamil" else 2,
        1,
        30,
    )
    barge_in_confirm_ms = bounded_int_env(
        f"{env_prefix}_BARGE_IN_CONFIRM_MS",
        80 if language == "tamil" else 100,
        60,
        350,
    )
    barge_in_min_voiced_frames = bounded_int_env(
        f"{env_prefix}_BARGE_IN_MIN_VOICED_FRAMES", 2, 2, 12
    )
    playback_mark_interval_ms = bounded_int_env(
        "PLIVO_PLAYBACK_CHECKPOINT_INTERVAL_MS",
        DEFAULT_PLAYBACK_MARK_INTERVAL_MS,
        100,
        1000,
    )
    inactivity_policy = CallInactivityPolicy(
        reprompt_seconds=bounded_int_env(
            "CALL_INACTIVITY_REPROMPT_SECONDS", 15, 5, 120
        ),
        hangup_seconds=bounded_int_env(
            "CALL_INACTIVITY_HANGUP_SECONDS", 10, 3, 60
        ),
    )
    session_ready = asyncio.Event()
    greeting_completed = asyncio.Event()
    inactivity_wakeup = asyncio.Event()
    openai_failed = asyncio.Event()
    openai_error: Optional[str] = None
    background_writes: set[asyncio.Task] = set()
    customer_requested_end = False
    pending_tool_call: Optional[tuple[str, str]] = None
    pending_route_call: Optional[tuple[str, dict[str, Any]]] = None
    pending_human_transfer: Optional[dict[str, Any]] = None
    graceful_hangup_started = False
    closing_playback_complete = asyncio.Event()

    def persist_snapshot(
        lines: list[str], usage: dict, speaker: Optional[str] = None,
        message: Optional[str] = None, event_id: Optional[str] = None,
    ) -> None:
        """Write call observability on a separate connection outside the audio loop."""
        if not call_sid:
            return
        conn = get_db_connection()
        try:
            if speaker and message:
                save_conversation(conn, customer_id, speaker, message, call_sid=call_sid, event_id=event_id)
            cost = estimate_openai_cost_usd(
                usage, model, language, transcription_model,
            )
            cur = conn.cursor()
            cur.execute("""UPDATE call_logs SET
                transcript=IF(total_turns<=%s,%s,transcript),total_turns=GREATEST(total_turns,%s),
                input_audio_tokens=GREATEST(input_audio_tokens,%s),
                output_audio_tokens=GREATEST(output_audio_tokens,%s),
                input_text_tokens=GREATEST(input_text_tokens,%s),
                output_text_tokens=GREATEST(output_text_tokens,%s),
                estimated_openai_cost_usd=GREATEST(estimated_openai_cost_usd,%s)
                WHERE call_sid=%s""", (
                len(lines), "\n".join(lines), len(lines), usage["input_audio"], usage["output_audio"],
                usage["input_text"], usage["output_text"], cost, call_sid,
            ))
            conn.commit()
        finally:
            conn.close()

    def schedule_persist(speaker: Optional[str] = None, message: Optional[str] = None,
                         event_id: Optional[str] = None) -> None:
        task = asyncio.create_task(asyncio.to_thread(
            persist_snapshot, list(transcript_lines), dict(usage_totals), speaker, message, event_id,
        ))
        background_writes.add(task)
        def finished(done: asyncio.Task) -> None:
            background_writes.discard(done)
            try:
                done.result()
            except Exception as exc:
                print(f"[OpenAI Realtime] background persistence failed: {exc}")
        task.add_done_callback(finished)

    url = f"wss://api.openai.com/v1/realtime?model={model}"
    # The Realtime API is GA. Sending the retired OpenAI-Beta header forces the
    # disabled beta protocol and closes the socket with
    # `invalid_request_error.beta_api_shape_disabled`.
    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        print(
            "[OpenAI Realtime] connecting | "
            f"model={model} voice_type={voice_type} voice={voice_label} "
            f"language={language} prompt_profile={conversation_profile}"
        )
        async with websockets.connect(
            url,
            additional_headers=headers,
            max_size=None,
            open_timeout=12,
            ping_interval=20,
            ping_timeout=20,
        ) as openai_ws:
            async def graceful_customer_hangup() -> None:
                nonlocal graceful_hangup_started
                if graceful_hangup_started or not call_sid:
                    return
                graceful_hangup_started = True
                sent_ms = response_audio_sent_bytes // PCMU_BYTES_PER_MILLISECOND
                remaining_seconds = max(
                    0.0, (sent_ms - response_audio_played_ms) / 1000
                )
                try:
                    await asyncio.wait_for(
                        closing_playback_complete.wait(),
                        timeout=min(max(remaining_seconds + 1.25, 1.5), 12.0),
                    )
                except asyncio.TimeoutError:
                    # Provider checkpoint delivery is best-effort. The timeout
                    # is based on remaining audio, so the farewell still has
                    # time to play before this fallback termination.
                    pass
                try:
                    cursor = db.cursor()
                    cursor.execute(
                        """UPDATE call_logs
                           SET conversation_end_reason=COALESCE(
                               conversation_end_reason, 'customer_goodbye'
                           )
                           WHERE call_sid=%s""",
                        (call_sid,),
                    )
                    db.commit()
                except Exception as exc:
                    print(f"[OpenAI Realtime] failed to save end reason: {exc}")
                try:
                    await asyncio.to_thread(
                        get_telephony_provider(db, call_organization_id).terminate_call,
                        call_id=call_sid,
                        request_id=None,
                    )
                    print(
                        "[OpenAI Realtime] customer farewell played; "
                        f"terminated call={call_sid}"
                    )
                except Exception as exc:
                    print(
                        "[OpenAI Realtime] graceful provider hangup failed | "
                        f"call={call_sid} error={type(exc).__name__}"
                    )

            def schedule_graceful_customer_hangup() -> None:
                if graceful_hangup_started:
                    return
                task = asyncio.create_task(graceful_customer_hangup())
                background_writes.add(task)
                task.add_done_callback(background_writes.discard)

            def note_caller_activity() -> None:
                inactivity_policy.note_activity()
                inactivity_wakeup.set()

            def note_assistant_state_change() -> None:
                inactivity_policy.note_assistant_state_change()
                inactivity_wakeup.set()

            def call_is_listening_for_customer() -> bool:
                sent_ms = response_audio_sent_bytes // PCMU_BYTES_PER_MILLISECOND
                has_unplayed_audio = bool(
                    response_item_id and sent_ms > response_audio_played_ms
                )
                return not (
                    response_in_progress
                    or active_input_item_id
                    or has_unplayed_audio
                    or customer_requested_end
                    or graceful_hangup_started
                )

            async def confirm_barge_in(item_id: str) -> None:
                """Stop playback quickly after a short, credible caller-speech window."""
                nonlocal response_item_id, response_audio_sent_bytes
                nonlocal response_audio_played_ms, response_last_mark_ms
                nonlocal interruption_count, suppress_response_audio
                nonlocal cancelled_response_count
                await asyncio.sleep(barge_in_confirm_ms / 1000)
                if (
                    active_input_item_id != item_id
                    or item_id in provisional_interrupted_items
                    or not stream_sid
                    or not response_item_id
                ):
                    return
                frames = barge_in_rms_frames.get(item_id, [])
                voiced_frames = sum(1 for value in frames if value >= turn_voiced_rms)
                if not is_credible_barge_in(
                    frames,
                    voiced_threshold=turn_voiced_rms,
                    minimum_peak_rms=max(turn_min_peak_rms, turn_voiced_rms),
                    minimum_voiced_frames=barge_in_min_voiced_frames,
                ):
                    print(
                        "[OpenAI Realtime] barge-in | "
                        "possible_speech=true confirmed_speech=false "
                        f"language={language} duration_ms={barge_in_confirm_ms} "
                        f"voiced_frames={voiced_frames} "
                        f"peak_rms={max(frames, default=0):.1f} "
                        f"average_rms={(sum(frames) / len(frames)) if frames else 0:.1f} "
                        f"assistant_speaking=true response_id={current_response_id} "
                        "cancel_sent=false plivo_clear_sent=false "
                        "rejection_reason=insufficient_voiced_audio"
                    )
                    return
                sent_ms = response_audio_sent_bytes // PCMU_BYTES_PER_MILLISECOND
                if sent_ms <= response_audio_played_ms:
                    return
                interrupted_item_id = response_item_id
                audio_end_ms = min(response_audio_played_ms, sent_ms)
                await websocket.send_json(clear_audio(stream_sid))
                if (
                    response_in_progress
                    and current_response_id not in cancel_sent_response_ids
                ):
                    await openai_ws.send(json.dumps({"type": "response.cancel"}))
                    if current_response_id:
                        cancel_sent_response_ids.add(current_response_id)
                await openai_ws.send(json.dumps({
                    "type": "conversation.item.truncate",
                    "item_id": interrupted_item_id,
                    "content_index": 0,
                    "audio_end_ms": audio_end_ms,
                }))
                interrupted_item_ids.add(interrupted_item_id)
                if current_response_id:
                    interrupted_response_ids.add(current_response_id)
                provisional_interrupted_items.add(item_id)
                interruption_count += 1
                cancelled_response_count += 1
                suppress_response_audio = True
                response_item_id = None
                response_audio_sent_bytes = 0
                response_audio_played_ms = 0
                response_last_mark_ms = 0
                print(
                    "[OpenAI Realtime] barge-in | "
                    "possible_speech=true confirmed_speech=true "
                    f"language={language} item={item_id} response_id={current_response_id} "
                    f"duration_ms={barge_in_confirm_ms} voiced_frames={voiced_frames} "
                    f"peak_rms={max(frames, default=0):.1f} "
                    f"average_rms={(sum(frames) / len(frames)) if frames else 0:.1f} "
                    "assistant_speaking=true cancel_sent=true plivo_clear_sent=true"
                )

            session_tools = [_end_call_tool_definition(), _transfer_to_human_tool_definition()]
            if router_mode:
                session_tools.append(
                    _route_to_human_tool_definition(
                        [str(item["label"]) for item in ivr_menu.get("options", [])]
                    )
                )
            await openai_ws.send(json.dumps({
                "type": "session.update",
                "session": {
                    "type": "realtime",
                    "model": model,
                    "instructions": instructions,
                    "output_modalities": ["audio"],
                    "audio": {
                        "input": {
                            "format": {"type": "audio/pcmu"},
                            # Realtime consumes audio natively, but user text is
                            # produced only when a separate input transcription
                            # model is enabled. Without this block the completed
                            # transcription event never arrives.
                            "transcription": transcription_config,
                            # English needs a predictable silence bound; Tamil
                            # keeps semantic VAD behind its validated turn planner.
                            "turn_detection": build_turn_detection_config(language),
                        },
                        "output": {"format": {"type": "audio/pcmu"}, "voice": voice},
                    },
                    "tools": session_tools,
                    "tool_choice": "auto",
                },
            }))

            async def inactivity_watchdog() -> None:
                """Reprompt once, then end a post-answer call that stays silent."""
                nonlocal response_in_progress, customer_requested_end
                await greeting_completed.wait()
                print(
                    "[OpenAI Realtime] inactivity watchdog started | "
                    f"reprompt_seconds={inactivity_policy.reprompt_seconds} "
                    f"hangup_seconds={inactivity_policy.hangup_seconds}"
                )
                while not customer_requested_end and not graceful_hangup_started:
                    while not call_is_listening_for_customer():
                        if customer_requested_end or graceful_hangup_started:
                            await asyncio.Future()
                        await asyncio.sleep(0.1)

                    observed_revision = inactivity_policy.state_revision
                    inactivity_wakeup.clear()
                    if observed_revision != inactivity_policy.state_revision:
                        continue
                    timeout_seconds = inactivity_policy.timeout_seconds
                    wait_started_at = time.monotonic()
                    try:
                        await asyncio.wait_for(
                            inactivity_wakeup.wait(),
                            timeout=timeout_seconds,
                        )
                        continue
                    except asyncio.TimeoutError:
                        pass

                    if not call_is_listening_for_customer():
                        continue
                    action = inactivity_policy.action_after_timeout(
                        observed_revision
                    )
                    if action == "activity":
                        continue
                    if action == "reprompt":
                        idle_elapsed_seconds = time.monotonic() - wait_started_at
                        response_in_progress = True
                        await openai_ws.send(json.dumps({
                            "type": "response.create",
                            "response": {
                                "output_modalities": ["audio"],
                                "instructions": inactivity_reprompt_instruction(
                                    response_language
                                ),
                            },
                        }))
                        print(
                            "[OpenAI Realtime] caller inactivity reprompt | "
                            f"call={call_sid} language={response_language} "
                            f"idle_seconds={idle_elapsed_seconds:.2f}"
                        )
                        continue

                    if call_sid:
                        cursor = db.cursor()
                        cursor.execute(
                            """UPDATE call_logs
                               SET conversation_end_reason='inactivity_timeout'
                               WHERE call_sid=%s""",
                            (call_sid,),
                        )
                        db.commit()
                    customer_requested_end = True
                    idle_elapsed_seconds = time.monotonic() - wait_started_at
                    response_in_progress = True
                    await openai_ws.send(json.dumps({
                        "type": "response.create",
                        "response": {
                            "output_modalities": ["audio"],
                            "instructions": inactivity_goodbye_instruction(
                                response_language
                            ),
                        },
                    }))
                    print(
                        "[OpenAI Realtime] caller inactivity goodbye requested | "
                        f"call={call_sid} language={response_language} "
                        f"idle_seconds={idle_elapsed_seconds:.2f}"
                    )
                    break
                # The bridge's Plivo/OpenAI reader tasks own socket lifetime.
                # Stay pending until one of them ends and cancels this watchdog.
                await asyncio.Future()

            async def trigger_latest_response() -> None:
                """Create one response only for the newest validated customer turn."""
                nonlocal response_in_progress, latest_intent
                async with response_lock:
                    if response_in_progress or not pending_response_items or not stream_sid:
                        return
                    item_id = pending_response_items.pop()
                    pending_response_items.clear()
                    turn_id = turn_sequence_by_item.get(item_id, 0)
                    if turn_id != latest_customer_turn_id:
                        validated_transcripts.pop(item_id, None)
                        return
                    transcript = validated_transcripts.pop(item_id, "")
                    if not transcript or is_stop_intent(transcript):
                        return
                    latest_intent = classify_intent(transcript, response_language)
                    response_in_progress = True
                    await openai_ws.send(json.dumps({
                        "type": "response.create",
                        "response": {
                            "output_modalities": ["audio"],
                            "metadata": {
                                "validated_input_item_id": item_id,
                                "latest_turn_id": str(turn_id),
                                "intent": latest_intent,
                                "turn_gate_profile": turn_gate_profile,
                            },
                            "instructions": _validated_turn_instruction(
                                transcript,
                                response_language,
                                recent_assistant_text,
                                knowledge_chunks=[],
                                ending=is_end_call_intent(
                                    transcript, response_language
                                ),
                            ),
                        },
                    }))

            async def process_validated_turn(item_id: str) -> None:
                """Validate audio+ASR, discard stale turns, and queue only the newest."""
                nonlocal false_turn_count, interruption_count, suppress_response_audio
                nonlocal response_item_id, response_audio_sent_bytes
                nonlocal response_audio_played_ms, response_last_mark_ms
                nonlocal response_latency_started_at, customer_requested_end
                nonlocal latest_customer_turn_id, latest_intent, response_language
                nonlocal stop_intent_count, callback_intent_count
                nonlocal end_call_intent_count, cancelled_response_count
                if (
                    item_id in processed_input_items
                    or item_id not in pending_transcripts
                    or item_id not in turn_stats
                ):
                    return
                text, event_id = pending_transcripts.pop(item_id)
                stats = turn_stats.pop(item_id)
                barge_in_rms_frames.pop(item_id, None)
                assistant_reference = " ".join(
                    part for part in (
                        recent_assistant_text,
                        "".join(assistant_transcript_parts),
                    ) if part
                )
                accepted, reason = validate_turn(
                    text,
                    stats,
                    assistant_reference,
                    minimum_duration_ms=turn_min_duration_ms,
                    minimum_peak_rms=turn_min_peak_rms,
                    minimum_voiced_frames=turn_min_voiced_frames,
                )
                processed_input_items.add(item_id)
                if not accepted:
                    false_turn_count += 1
                    await openai_ws.send(json.dumps({
                        "type": "conversation.item.delete",
                        "item_id": item_id,
                    }))
                    print(
                        "[OpenAI Realtime] turn rejected | "
                        f"language={language} item={item_id} reason={reason} "
                        f"duration_ms={stats.duration_ms} peak_rms={stats.peak_rms:.1f} "
                        f"average_rms={stats.average_rms:.1f} "
                        f"voiced_frames={stats.voiced_frames}"
                    )
                    return

                latest_customer_turn_id += 1
                turn_sequence_by_item[item_id] = latest_customer_turn_id
                latest_intent = classify_intent(text, response_language)
                transcript_lines.append(f"user: {text}")
                schedule_persist("user", text, event_id)
                if response_latency_started_at is None:
                    response_latency_started_at = time.monotonic()

                if latest_intent == "language_switch":
                    response_language = (
                        "english" if "english" in text.casefold() else "tamil"
                    )
                if latest_intent == "stop":
                    stop_intent_count += 1
                elif latest_intent == "callback":
                    callback_intent_count += 1
                    if call_sid:
                        cur = db.cursor()
                        cur.execute(
                            """UPDATE call_logs SET followup_required=TRUE,
                               lead_status='callback_requested',
                               conversation_end_reason='callback_requested'
                               WHERE call_sid=%s""",
                            (call_sid,),
                        )
                        db.commit()
                        try:
                            from app.services import callback_service
                            callback_service.ensure_for_call_sid(
                                db,
                                organization_id=organization_id,
                                call_sid=call_sid,
                                source="realtime",
                            )
                        except Exception as callback_err:
                            print(f"[OpenAI Realtime] callback task persistence failed: {callback_err}")
                elif latest_intent in {"end_call", "not_interested"}:
                    end_call_intent_count += 1
                    customer_requested_end = True
                    if call_sid:
                        cur = db.cursor()
                        if is_do_not_call_intent(text):
                            end_reason = "customer_do_not_call"
                        elif is_not_interested_intent(text):
                            end_reason = "customer_not_interested"
                        else:
                            end_reason = "customer_end_request"
                        cur.execute(
                            """UPDATE call_logs SET
                               lead_status=CASE WHEN %s='customer_not_interested'
                                   THEN 'not_interested' ELSE lead_status END,
                               conversation_end_reason=%s
                               WHERE call_sid=%s""",
                            (end_reason, end_reason, call_sid),
                        )
                        if is_do_not_call_intent(text):
                            phone = re.sub(r"\D+", "", str(customer.get("phone") or ""))
                            phone_hash = hashlib.sha256(phone.encode("utf-8")).hexdigest()
                            cur.execute(
                                """UPDATE customers SET do_not_call=TRUE,
                                   is_active=FALSE, customer_status='do_not_call'
                                   WHERE id=%s""",
                                (customer_id,),
                            )
                            if phone:
                                cur.execute(
                                    """INSERT INTO suppression_list
                                       (organization_id,phone_hash,reason,source)
                                       VALUES (%s,%s,'customer_opt_out','realtime_voice')
                                       ON DUPLICATE KEY UPDATE
                                         reason=VALUES(reason),source=VALUES(source)""",
                                    (
                                        organization_id,
                                        phone_hash,
                                    ),
                                )
                                cur.execute(
                                    """INSERT INTO audit_logs (organization_id,action,resource_type,resource_id,result,metadata_json)
                                       VALUES (%s,'suppression_added','customer',%s,'success',%s)""",
                                    (
                                        organization_id,
                                        str(customer_id),
                                        json.dumps({"source": "realtime_voice", "call_sid": call_sid, "intent": "do_not_call"}),
                                    ),
                                )
                        db.commit()

                # A new validated turn supersedes every older pending response.
                pending_response_items.clear()
                validated_transcripts.clear()
                if latest_intent != "stop":
                    validated_transcripts[item_id] = text
                    pending_response_items.append(item_id)

                sent_ms = response_audio_sent_bytes // PCMU_BYTES_PER_MILLISECOND
                has_unplayed_audio = bool(
                    response_item_id and sent_ms > response_audio_played_ms
                )
                if stream_sid and has_unplayed_audio:
                    await websocket.send_json(clear_audio(stream_sid))
                    interrupted_item_id = response_item_id
                    audio_end_ms = min(response_audio_played_ms, sent_ms)
                    if (
                        response_in_progress
                        and current_response_id not in cancel_sent_response_ids
                    ):
                        await openai_ws.send(json.dumps({"type": "response.cancel"}))
                        if current_response_id:
                            cancel_sent_response_ids.add(current_response_id)
                    await openai_ws.send(json.dumps({
                        "type": "conversation.item.truncate",
                        "item_id": interrupted_item_id,
                        "content_index": 0,
                        "audio_end_ms": audio_end_ms,
                    }))
                    interrupted_item_ids.add(interrupted_item_id)
                    if current_response_id:
                        interrupted_response_ids.add(current_response_id)
                    interruption_count += 1
                    cancelled_response_count += 1
                    suppress_response_audio = True
                    response_item_id = None
                    response_audio_sent_bytes = 0
                    response_audio_played_ms = 0
                    response_last_mark_ms = 0
                if not response_in_progress:
                    await trigger_latest_response()

            async def from_plivo():
                nonlocal stream_sid, call_sid, response_audio_played_ms, greeting_requested
                nonlocal response_in_progress, suppress_response_audio
                nonlocal cancelled_response_count
                nonlocal latest_voiced_frame_at
                async for raw in websocket.iter_text():
                    event = json.loads(raw)
                    kind = event.get("event")
                    if kind == "start":
                        call_sid, stream_sid = parse_start(event)
                        if call_sid and stream_sid:
                            cur = db.cursor()
                            cur.execute(
                                """UPDATE call_logs SET provider_call_id=%s,call_sid=%s,
                                   provider_stream_id=%s,stream_sid=%s
                                   WHERE correlation_id=%s
                                     AND (provider_stream_id IS NULL OR provider_stream_id=%s)""",
                                (
                                    call_sid, call_sid, stream_sid, stream_sid,
                                    correlation_id, stream_sid,
                                ),
                            )
                            db.commit()
                            cur.execute(
                                "SELECT provider_stream_id FROM call_logs WHERE correlation_id=%s",
                                (correlation_id,),
                            )
                            owner = cur.fetchone() or {}
                            if owner.get("provider_stream_id") != stream_sid:
                                print(
                                    "[OpenAI Realtime] duplicate Plivo stream rejected | "
                                    f"call={call_sid} duplicate={stream_sid}"
                                )
                                call_sid = None
                                return
                        if call_sid:
                            try:
                                call_log_service.update_call_log_status(db, call_sid, "in-progress")
                            except Exception as exc:
                                print(f"[OpenAI Realtime] call log start failed: {exc}")
                        try:
                            await asyncio.wait_for(session_ready.wait(), timeout=10)
                        except asyncio.TimeoutError:
                            raise RuntimeError(
                                "OpenAI Realtime session was not accepted within 10 seconds. "
                                "Check API key, billing, model access and terminal API errors."
                            )
                        print(
                            f"[OpenAI Realtime] Plivo started | call={call_sid} "
                            f"stream={stream_sid}; requesting greeting"
                        )
                        if not greeting_requested:
                            greeting_requested = True
                            response_in_progress = True
                            first_turn_instructions = (
                                build_router_greeting_instruction(language, ivr_menu, organization_name)
                                if router_mode else
                                _greeting_instruction(customer, language, organization_name, call_direction=call_direction)
                            )
                            await openai_ws.send(json.dumps({
                                "type": "response.create",
                                "response": {
                                    "output_modalities": ["audio"],
                                    "instructions": first_turn_instructions,
                                },
                            }))
                    elif kind == "media":
                        payload = media_payload(event)
                        if payload:
                            pcmu = base64.b64decode(payload)
                            frame_rms = mulaw_rms(pcmu)
                            recent_input_rms.append(frame_rms)
                            if frame_rms >= turn_voiced_rms:
                                latest_voiced_frame_at = time.monotonic()
                            if active_input_item_id:
                                turn_rms_frames.setdefault(active_input_item_id, []).append(frame_rms)
                                barge_in_rms_frames.setdefault(active_input_item_id, []).append(frame_rms)
                                if frame_rms >= turn_voiced_rms:
                                    turn_last_voiced_at[active_input_item_id] = time.monotonic()
                            if enhance_input:
                                payload = base64.b64encode(input_enhancer.process(pcmu)).decode("ascii")
                            await openai_ws.send(json.dumps({"type": "input_audio_buffer.append", "audio": payload}))
                    elif kind == "playedStream":
                        mark_item_id, played_ms = parse_playback_mark(
                            event.get("name") or ""
                        )
                        if mark_item_id == response_item_id and played_ms is not None:
                            response_audio_played_ms = max(response_audio_played_ms, played_ms)
                            if (
                                customer_requested_end
                                and response_last_mark_ms > 0
                                and response_audio_played_ms >= response_last_mark_ms
                            ):
                                closing_playback_complete.set()
                    elif kind == "stop":
                        # Plivo has ended media delivery. Stop generation now;
                        # continuing cannot reach the caller and wastes tokens.
                        if response_in_progress:
                            try:
                                if current_response_id not in cancel_sent_response_ids:
                                    await openai_ws.send(json.dumps({"type": "response.cancel"}))
                                    if current_response_id:
                                        cancel_sent_response_ids.add(current_response_id)
                                        interrupted_response_ids.add(current_response_id)
                                    cancelled_response_count += 1
                            except Exception:
                                pass
                        suppress_response_audio = True
                        response_in_progress = False
                        print("[OpenAI Realtime] Plivo stream stopped; generation cancelled")
                        break

            async def from_openai():
                nonlocal first_audio_at, response_latency_started_at, response_item_id, openai_error
                nonlocal response_audio_sent_bytes, response_audio_played_ms
                nonlocal response_last_mark_ms, interruption_count
                nonlocal suppress_response_audio
                nonlocal response_in_progress, recent_assistant_text
                nonlocal assistant_transcript_parts, active_input_item_id
                nonlocal customer_requested_end, pending_tool_call
                nonlocal pending_route_call, pending_human_transfer
                nonlocal current_response_id
                nonlocal latest_intent, latest_customer_turn_id
                nonlocal end_call_intent_count
                async for raw in openai_ws:
                    event = json.loads(raw)
                    kind = event.get("type")
                    if kind == "error":
                        error = event.get("error") or {}
                        openai_error = json.dumps(error, ensure_ascii=False)
                        openai_failed.set()
                        print(f"[OpenAI Realtime][FATAL API ERROR] {openai_error}")
                    elif kind == "session.created":
                        print("[OpenAI Realtime] session created; waiting for configured session")
                    elif kind == "session.updated":
                        session_ready.set()
                        print(f"[OpenAI Realtime] session ready | model={model} voice={voice_label}")
                    elif kind == "response.created":
                        response_in_progress = True
                        note_assistant_state_change()
                        current_response_id = (event.get("response") or {}).get("id")
                        print(
                            "[OpenAI Realtime] response generation started | "
                            f"response_id={current_response_id}"
                        )
                    elif kind == "input_audio_buffer.speech_started":
                        note_caller_activity()
                        input_item_id = event.get("item_id") or f"vad_{event.get('event_id') or time.monotonic_ns()}"
                        active_input_item_id = input_item_id
                        turn_started_at[input_item_id] = time.monotonic()
                        turn_audio_start_ms[input_item_id] = int(event.get("audio_start_ms") or 0)
                        turn_rms_frames[input_item_id] = list(recent_input_rms)
                        if (
                            latest_voiced_frame_at is not None
                            and any(value >= turn_voiced_rms for value in recent_input_rms)
                        ):
                            turn_last_voiced_at[input_item_id] = latest_voiced_frame_at
                        barge_in_rms_frames[input_item_id] = []
                        sent_ms = response_audio_sent_bytes // PCMU_BYTES_PER_MILLISECOND
                        has_unplayed_audio = bool(
                            response_item_id and sent_ms > response_audio_played_ms
                        )
                        if stream_sid and has_unplayed_audio:
                            if language == "english":
                                # This is the established English behavior:
                                # OpenAI semantic VAD interrupts generation and
                                # Plivo playback is cleared immediately.
                                await websocket.send_json(clear_audio(stream_sid))
                                if response_item_id:
                                    interrupted_item_ids.add(response_item_id)
                                if current_response_id:
                                    interrupted_response_ids.add(current_response_id)
                                suppress_response_audio = True
                                response_item_id = None
                                response_audio_sent_bytes = 0
                                response_audio_played_ms = 0
                                response_last_mark_ms = 0
                            else:
                                task = asyncio.create_task(confirm_barge_in(input_item_id))
                                background_writes.add(task)
                                task.add_done_callback(background_writes.discard)
                    elif kind == "input_audio_buffer.speech_stopped":
                        input_item_id = event.get("item_id") or active_input_item_id
                        if input_item_id:
                            tracking_item_id = active_input_item_id or input_item_id
                            audio_end_ms = int(event.get("audio_end_ms") or 0)
                            audio_start_ms = turn_audio_start_ms.pop(tracking_item_id, 0)
                            if audio_end_ms > audio_start_ms:
                                duration_ms = audio_end_ms - audio_start_ms
                            else:
                                duration_ms = int(
                                    (time.monotonic() - turn_started_at.get(tracking_item_id, time.monotonic()))
                                    * 1000
                                )
                            turn_stats[input_item_id] = build_turn_stats(
                                turn_rms_frames.pop(tracking_item_id, []),
                                duration_ms,
                                turn_voiced_rms,
                            )
                            # Start at the last locally observed voiced frame so
                            # telemetry includes semantic-VAD finalization time.
                            response_latency_started_at = turn_last_voiced_at.pop(
                                tracking_item_id, time.monotonic()
                            )
                            active_input_item_id = None
                            if language == "tamil":
                                await process_validated_turn(input_item_id)
                    elif kind == "conversation.item.input_audio_transcription.completed":
                        transcription_usage = event.get("usage") or {}
                        usage_totals["transcription_input_audio"] += int(
                            (transcription_usage.get("input_token_details") or {}).get("audio_tokens")
                            or transcription_usage.get("input_tokens")
                            or 0
                        )
                        usage_totals["transcription_output_text"] += int(
                            transcription_usage.get("output_tokens") or 0
                        )
                        text = (event.get("transcript") or "").strip()
                        input_item_id = event.get("item_id") or ""
                        if input_item_id:
                            if language == "english":
                                if text:
                                    latest_customer_turn_id += 1
                                    latest_intent = classify_intent(text, "english")
                                    transcript_lines.append(f"user: {text}")
                                    schedule_persist(
                                        "user", text, event.get("event_id")
                                    )
                                    if latest_intent in {"end_call", "not_interested"}:
                                        end_call_intent_count += 1
                                        customer_requested_end = True
                                        if call_sid:
                                            cur = db.cursor()
                                            if is_do_not_call_intent(text):
                                                end_reason = "customer_do_not_call"
                                            elif is_not_interested_intent(text):
                                                end_reason = "customer_not_interested"
                                            else:
                                                end_reason = "customer_end_request"
                                            cur.execute(
                                                """UPDATE call_logs SET
                                                   lead_status=CASE WHEN %s='customer_not_interested'
                                                       THEN 'not_interested' ELSE lead_status END,
                                                   conversation_end_reason=%s
                                                   WHERE call_sid=%s""",
                                                (end_reason, end_reason, call_sid),
                                            )
                                            if is_do_not_call_intent(text):
                                                phone = re.sub(r"\D+", "", str(customer.get("phone") or ""))
                                                phone_hash = hashlib.sha256(phone.encode("utf-8")).hexdigest()
                                                cur.execute(
                                                    """UPDATE customers SET do_not_call=TRUE,
                                                       is_active=FALSE, customer_status='do_not_call'
                                                       WHERE id=%s""",
                                                    (customer_id,),
                                                )
                                                if phone:
                                                    cur.execute(
                                                        """INSERT INTO suppression_list
                                                           (organization_id,phone_hash,reason,source)
                                                           VALUES (%s,%s,'customer_opt_out','realtime_voice')
                                                           ON DUPLICATE KEY UPDATE
                                                             reason=VALUES(reason),source=VALUES(source)""",
                                                        (
                                                            organization_id,
                                                            phone_hash,
                                                        ),
                                                    )
                                                    cur.execute(
                                                        """INSERT INTO audit_logs (organization_id,action,resource_type,resource_id,result,metadata_json)
                                                           VALUES (%s,'suppression_added','customer',%s,'success',%s)""",
                                                        (
                                                            organization_id,
                                                            str(customer_id),
                                                            json.dumps({"source": "realtime_voice", "call_sid": call_sid, "intent": "do_not_call"}),
                                                        ),
                                                    )
                                            db.commit()
                            else:
                                pending_transcripts[input_item_id] = (
                                    text,
                                    event.get("event_id"),
                                )
                                await process_validated_turn(input_item_id)
                    elif kind in {"response.output_item.added", "response.output_item.created"}:
                        new_item_id = ((event.get("item") or {}).get("id"))
                        event_response_id = event.get("response_id") or current_response_id
                        if (
                            new_item_id
                            and new_item_id not in interrupted_item_ids
                            and event_response_id not in interrupted_response_ids
                        ):
                            suppress_response_audio = False
                        response_item_id = new_item_id
                        assistant_transcript_parts = []
                        response_audio_sent_bytes = 0
                        response_audio_played_ms = 0
                        response_last_mark_ms = 0
                    elif kind == "response.output_item.done":
                        done_item = event.get("item") or {}
                        if done_item.get("type") == "function_call" and done_item.get("name") == "end_call":
                            call_id = done_item.get("call_id") or ""
                            try:
                                args = json.loads(done_item.get("arguments") or "{}")
                            except (TypeError, ValueError):
                                args = {}
                            reason = args.get("reason") or "other"
                            if call_id:
                                pending_tool_call = (call_id, reason)
                            print(
                                "[OpenAI Realtime] model called end_call tool | "
                                f"reason={reason} call={call_sid}"
                            )
                            if call_sid:
                                end_reason_map = {
                                    "customer_goodbye": "customer_goodbye",
                                    "customer_not_interested": "customer_not_interested",
                                    "customer_do_not_call": "customer_do_not_call",
                                    "other": "customer_end_request",
                                }
                                end_reason = end_reason_map.get(reason, "customer_end_request")
                                cur = db.cursor()
                                cur.execute(
                                    """UPDATE call_logs SET
                                       lead_status=CASE WHEN %s='customer_not_interested'
                                           THEN 'not_interested' ELSE lead_status END,
                                       conversation_end_reason=%s
                                       WHERE call_sid=%s""",
                                    (end_reason, end_reason, call_sid),
                                )
                                if end_reason == "customer_do_not_call":
                                    phone = re.sub(r"\D+", "", str(customer.get("phone") or ""))
                                    phone_hash = hashlib.sha256(phone.encode("utf-8")).hexdigest()
                                    cur.execute(
                                        """UPDATE customers SET do_not_call=TRUE,
                                           is_active=FALSE, customer_status='do_not_call'
                                           WHERE id=%s""",
                                        (customer_id,),
                                    )
                                    if phone:
                                        cur.execute(
                                            """INSERT INTO suppression_list
                                               (organization_id,phone_hash,reason,source)
                                               VALUES (%s,%s,'customer_opt_out','realtime_voice')
                                               ON DUPLICATE KEY UPDATE
                                                 reason=VALUES(reason),source=VALUES(source)""",
                                            (
                                                organization_id,
                                                phone_hash,
                                            ),
                                        )
                                db.commit()
                        elif done_item.get("type") == "function_call" and done_item.get("name") == "route_to_human":
                            call_id = done_item.get("call_id") or ""
                            try:
                                args = json.loads(done_item.get("arguments") or "{}")
                            except (TypeError, ValueError):
                                args = {}
                            department = str(args.get("department") or "").strip()
                            routed = None
                            if department and call_log_id:
                                routed = ivr_service.route_selection(
                                    db, organization_id=organization_id, call_log_id=call_log_id,
                                    speech_text=department,
                                )
                            print(
                                "[OpenAI Realtime] model called route_to_human tool | "
                                f"department={department} route={routed} call={call_sid}"
                            )
                            if routed and routed.get("route_type") == "ai":
                                routed_campaign = campaign_service.get_campaign_by_id(
                                    db, int(routed["campaign_id"]), organization_id,
                                )
                                routed_instructions = _instructions(
                                    language, operator, routed_campaign, memory, organization_name,
                                )
                                await openai_ws.send(json.dumps({
                                    "type": "session.update",
                                    "session": {
                                        "type": "realtime",
                                        "instructions": routed_instructions,
                                        "tools": [_end_call_tool_definition(), _transfer_to_human_tool_definition()],
                                        "tool_choice": "auto",
                                    },
                                }))
                                if call_id:
                                    await openai_ws.send(json.dumps({
                                        "type": "conversation.item.create",
                                        "item": {
                                            "type": "function_call_output",
                                            "call_id": call_id,
                                            "output": json.dumps({"routed": True, "mode": "ai"}),
                                        },
                                    }))
                            elif routed and routed.get("route_type") == "human" and call_id:
                                pending_route_call = (call_id, routed)
                            elif call_id:
                                await openai_ws.send(json.dumps({
                                    "type": "conversation.item.create",
                                    "item": {
                                        "type": "function_call_output",
                                        "call_id": call_id,
                                        "output": json.dumps({"routed": False}),
                                    },
                                }))
                        elif done_item.get("type") == "function_call" and done_item.get("name") == "transfer_to_human":
                            call_id = done_item.get("call_id") or ""
                            destination = None
                            if call_log_id:
                                cur = db.cursor()
                                cur.execute(
                                    """SELECT id,name FROM staff_destinations
                                       WHERE organization_id=%s AND is_active=TRUE
                                       ORDER BY priority ASC LIMIT 1""",
                                    (organization_id,),
                                )
                                destination = cur.fetchone()
                            print(
                                "[OpenAI Realtime] model called transfer_to_human tool | "
                                f"destination={destination} call={call_sid}"
                            )
                            if destination and call_id:
                                pending_route_call = (call_id, {
                                    "route_type": "human",
                                    "destination_id": int(destination["id"]),
                                    "destination_name": destination.get("name"),
                                })
                            elif call_id:
                                await openai_ws.send(json.dumps({
                                    "type": "conversation.item.create",
                                    "item": {
                                        "type": "function_call_output",
                                        "call_id": call_id,
                                        "output": json.dumps({
                                            "routed": False, "reason": "no_destination_configured",
                                        }),
                                    },
                                }))
                    elif kind == "response.output_audio_transcript.delta":
                        delta_text = event.get("delta") or ""
                        if delta_text:
                            assistant_transcript_parts.append(delta_text)
                    elif kind == "response.output_audio_transcript.done":
                        assistant_text = (event.get("transcript") or "").strip()
                        transcript_response_id = (
                            event.get("response_id") or current_response_id
                        )
                        transcript_interrupted = (
                            event.get("item_id") in interrupted_item_ids
                            or transcript_response_id in interrupted_response_ids
                        )
                        if assistant_text and not transcript_interrupted:
                            recent_assistant_text = assistant_text
                        if assistant_text and not transcript_interrupted:
                            word_count = count_response_words(assistant_text)
                            sentence_count = count_response_sentences(assistant_text)
                            assistant_response_word_counts.append(word_count)
                            assistant_response_sentence_counts.append(sentence_count)
                            transcript_lines.append(f"assistant: {assistant_text}")
                            schedule_persist("assistant", assistant_text, event.get("event_id"))
                    elif kind in {"response.output_audio.delta", "response.audio.delta"}:
                        delta = event.get("delta")
                        event_response_id = event.get("response_id") or current_response_id
                        if (
                            delta
                            and stream_sid
                            and not suppress_response_audio
                            and event_response_id not in interrupted_response_ids
                        ):
                            now = time.monotonic()
                            if first_audio_at is None:
                                first_audio_at = now
                            if response_latency_started_at is not None:
                                turn_latencies.append(caller_perceived_latency_ms(
                                    response_latency_started_at, now
                                ))
                                response_latency_started_at = None
                            await websocket.send_json(play_audio(delta))
                            response_audio_sent_bytes += len(base64.b64decode(delta))
                            sent_ms = response_audio_sent_bytes // PCMU_BYTES_PER_MILLISECOND
                            if (
                                response_item_id
                                and sent_ms - response_last_mark_ms >= playback_mark_interval_ms
                            ):
                                await websocket.send_json(checkpoint(
                                    stream_sid,
                                    playback_mark_name(response_item_id, sent_ms),
                                ))
                                response_last_mark_ms = sent_ms
                            if first_audio_at == now:
                                print("[OpenAI Realtime] first audio sent to Plivo")
                    elif kind in {"response.output_audio.done", "response.audio.done"}:
                        sent_ms = response_audio_sent_bytes // PCMU_BYTES_PER_MILLISECOND
                        if (
                            stream_sid and response_item_id and not suppress_response_audio
                            and sent_ms > response_last_mark_ms
                        ):
                            await websocket.send_json(checkpoint(
                                stream_sid,
                                playback_mark_name(response_item_id, sent_ms),
                            ))
                            response_last_mark_ms = sent_ms
                    elif kind == "response.done":
                        response_in_progress = False
                        note_assistant_state_change()
                        if greeting_requested and not greeting_completed.is_set():
                            greeting_completed.set()
                        response = event.get("response") or {}
                        status = response.get("status")
                        details = response.get("status_details")
                        print(f"[OpenAI Realtime] response done | status={status} details={details}")
                        usage = response.get("usage") or {}
                        inp, out = usage.get("input_token_details") or {}, usage.get("output_token_details") or {}
                        cached = inp.get("cached_tokens_details") or {}
                        usage_totals["input_audio"] += int(inp.get("audio_tokens") or 0)
                        usage_totals["input_text"] += int(inp.get("text_tokens") or 0)
                        usage_totals["output_audio"] += int(out.get("audio_tokens") or 0)
                        usage_totals["output_text"] += int(out.get("text_tokens") or 0)
                        usage_totals["cached_input_audio"] += int(cached.get("audio_tokens") or 0)
                        usage_totals["cached_input_text"] += int(cached.get("text_tokens") or 0)
                        usage_totals["total"] += int(usage.get("total_tokens") or 0)
                        schedule_persist()
                        current_response_id = None
                        if pending_tool_call is not None:
                            tool_call_id, tool_reason = pending_tool_call
                            pending_tool_call = None
                            end_call_intent_count += 1
                            await openai_ws.send(json.dumps({
                                "type": "conversation.item.create",
                                "item": {
                                    "type": "function_call_output",
                                    "call_id": tool_call_id,
                                    "output": json.dumps({"ended": True, "reason": tool_reason}),
                                },
                            }))
                            customer_requested_end = True
                            response_in_progress = True
                            await openai_ws.send(json.dumps({
                                "type": "response.create",
                                "response": {
                                    "output_modalities": ["audio"],
                                    "instructions": _validated_turn_instruction(
                                        "", response_language, recent_assistant_text, ending=True,
                                    ),
                                },
                            }))
                        elif pending_route_call is not None:
                            route_call_id, routed = pending_route_call
                            pending_route_call = None
                            await openai_ws.send(json.dumps({
                                "type": "conversation.item.create",
                                "item": {
                                    "type": "function_call_output",
                                    "call_id": route_call_id,
                                    "output": json.dumps({
                                        "routed": True, "mode": "human",
                                        "destination": routed.get("destination_name"),
                                    }),
                                },
                            }))
                            response_in_progress = True
                            connecting_line = (
                                "தொடர்பு படுத்துறேன், ஒரு நிமிஷம் பொறுங்க."
                                if language == "tamil"
                                else "Connecting you now, one moment."
                            )
                            await openai_ws.send(json.dumps({
                                "type": "response.create",
                                "response": {
                                    "output_modalities": ["audio"],
                                    "instructions": connecting_line,
                                },
                            }))
                            pending_human_transfer = routed
                        elif pending_human_transfer is not None:
                            routed = pending_human_transfer
                            pending_human_transfer = None
                            await perform_live_transfer(routed)
                        elif customer_requested_end and not pending_response_items:
                            schedule_graceful_customer_hangup()
                        elif language == "tamil":
                            await trigger_latest_response()

            async def perform_live_transfer(routed: dict[str, Any]) -> None:
                """Transfer the live call to the human destination the AI
                just routed to, reusing the exact mechanism the dashboard's
                manual "Transfer live call" button already uses and has
                already been tested against.
                """
                try:
                    cur = db.cursor()
                    cur.execute(
                        "SELECT id FROM app_users WHERE organization_id=%s ORDER BY id LIMIT 1",
                        (organization_id,),
                    )
                    owner = cur.fetchone()
                    if not owner:
                        print(
                            "[OpenAI Realtime] route_to_human transfer skipped: "
                            f"no admin user for org={organization_id}"
                        )
                        return
                    transfer = transfer_service.prepare_transfer(
                        db, organization_id=organization_id, call_log_id=call_log_id,
                        destination_id=int(routed["destination_id"]), actor_user_id=int(owner["id"]),
                        idempotency_key=f"ai-route-{call_log_id}",
                    )
                    if transfer.get("status") != "requested":
                        print(
                            "[OpenAI Realtime] route_to_human transfer not requested "
                            f"(existing status={transfer.get('status')}), skipping | call={call_sid}"
                        )
                        return
                    # Long-lived websocket process: re-read .env fresh instead of
                    # trusting whatever WEBHOOK_BASE_URL was cached at process
                    # start, since the tunnel URL changes on every restart.
                    load_dotenv(
                        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env")),
                        override=True,
                    )
                    base = (os.getenv("WEBHOOK_BASE_URL") or "").strip().rstrip("/")
                    if not base:
                        print("[OpenAI Realtime] route_to_human transfer skipped: WEBHOOK_BASE_URL is not set")
                        return
                    query = urlencode({"transfer_id": transfer["id"], "correlation_id": correlation_id})
                    answer_url = f"{base}/api/plivo/transfer-answer?{query}"
                    callback_url = f"{base}/api/plivo/transfer-update-callback?{query}"
                    print(
                        f"[OpenAI Realtime] route_to_human requesting Plivo transfer | "
                        f"transfer_id={transfer['id']} provider_call_id={transfer['provider_call_id']} "
                        f"answer_url={answer_url} call={call_sid}"
                    )
                    live_provider = get_telephony_provider(db, organization_id)
                    live_provider.transfer_call(
                        call_id=transfer["provider_call_id"], answer_url=answer_url,
                        callback_url=callback_url,
                    )
                    transfer_service.set_provider_accepted(db, organization_id, transfer["id"])
                    print(
                        f"[OpenAI Realtime] route_to_human transfer accepted by Plivo | "
                        f"transfer_id={transfer['id']} call={call_sid}"
                    )
                    # <Stream keepCallAlive="true"> keeps the call up when OUR
                    # side disconnects the media socket -- that is what frees
                    # the call to pick up the already-queued redirect above.
                    # Forcing Plivo to stop the stream via REST instead (an
                    # earlier attempt at this) caused Plivo to report the call
                    # as gone by the time it tried to fetch the redirect, so
                    # this intentional, graceful close is the correct path.
                    try:
                        await websocket.close()
                        print(f"[OpenAI Realtime] route_to_human closed our media stream to release the call | transfer_id={transfer['id']}")
                    except Exception as exc:
                        print(f"[OpenAI Realtime] route_to_human websocket close failed: {type(exc).__name__}: {exc}")
                except Exception as exc:
                    print(f"[OpenAI Realtime] route_to_human transfer failed: {type(exc).__name__}: {exc}")

            tasks = [
                asyncio.create_task(from_plivo()),
                asyncio.create_task(from_openai()),
                asyncio.create_task(inactivity_watchdog()),
            ]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                task.result()

    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception as exc:
        print(f"[OpenAI Realtime][BRIDGE FAILED] {type(exc).__name__}: {exc}")
    finally:
        if background_writes:
            await asyncio.gather(*list(background_writes), return_exceptions=True)
        duration = int(time.monotonic() - started_at)
        avg_latency = int(sum(turn_latencies) / len(turn_latencies)) if turn_latencies else None
        first_latency = turn_latencies[0] if turn_latencies else None
        maximum_latency = max(turn_latencies) if turn_latencies else None
        average_response_words = (
            round(
                sum(assistant_response_word_counts)
                / len(assistant_response_word_counts),
                2,
            )
            if assistant_response_word_counts else 0
        )
        maximum_response_words = max(assistant_response_word_counts, default=0)
        responses_exceeding_limits = sum(
            words > target_response_words_max
            or sentences > max_response_sentences
            for words, sentences in zip(
                assistant_response_word_counts,
                assistant_response_sentence_counts,
            )
        )
        short_response_compliance_rate = (
            round(
                100
                * (len(assistant_response_word_counts) - responses_exceeding_limits)
                / len(assistant_response_word_counts),
                2,
            )
            if assistant_response_word_counts else 100.0
        )
        if call_sid:
            try:
                call_log_service.finalize_call_log(
                    conn=db, call_sid=call_sid, status="completed", duration=duration,
                    transcript="\n".join(transcript_lines), customer_id=customer_id,
                )
                cur = db.cursor()
                cur.execute(
                    "UPDATE call_logs SET call_path='openai_realtime', voice_provider='openai', "
                    "stt_provider='openai', llm_provider='openai', tts_provider='openai', "
                    "realtime_model=%s, transcription_model=%s, realtime_voice=%s, voice_style_profile=%s, "
                    "knowledge_profile=%s, conversation_profile=%s, first_response_latency_ms=%s, "
                    "avg_response_latency_ms=%s, maximum_response_latency_ms=%s, "
                    "turn_gate_profile=%s, interruption_count=%s, false_turn_count=%s "
                    "WHERE call_sid=%s",
                    (
                        model, transcription_model, voice_label, voice_style_profile,
                        knowledge_profile, conversation_profile,
                        first_latency, avg_latency, maximum_latency, turn_gate_profile,
                        interruption_count, false_turn_count, call_sid,
                    ),
                )
                db.commit()
                cur.execute("SELECT id FROM call_logs WHERE call_sid=%s ORDER BY id DESC LIMIT 1", (call_sid,))
                row = cur.fetchone()
                if row:
                    cost = estimate_openai_cost_usd(
                        usage_totals, model, language, transcription_model,
                    )
                    cur.execute("""INSERT INTO realtime_usage
                        (call_log_id,model_name,voice_name,input_audio_tokens,output_audio_tokens,
                         input_text_tokens,output_text_tokens,cached_input_audio_tokens,
                         cached_input_text_tokens,estimated_cost_usd,usage_data)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", (
                        row["id"], model, voice_label, usage_totals["input_audio"], usage_totals["output_audio"],
                        usage_totals["input_text"], usage_totals["output_text"],
                        usage_totals["cached_input_audio"], usage_totals["cached_input_text"], cost,
                        json.dumps({
                            **usage_totals,
                            "prompt_estimate": prompt_metrics,
                            "legacy_campaign_estimated_tokens": 0,
                            "prompt_profile": CONVERSATION_POLICY_PROFILE,
                            "voice_type": voice_type,
                            "latest_intent": latest_intent,
                            "latest_customer_turn_id": latest_customer_turn_id,
                            "cancelled_assistant_responses": cancelled_response_count,
                            "stop_intent_count": stop_intent_count,
                            "callback_intent_count": callback_intent_count,
                            "end_call_intent_count": end_call_intent_count,
                            "average_assistant_response_words": average_response_words,
                            "maximum_assistant_response_words": maximum_response_words,
                            "responses_exceeding_limits": responses_exceeding_limits,
                            "short_response_compliance_rate": short_response_compliance_rate,
                            "cost_estimation_version": COST_ESTIMATION_VERSION,
                            "cache_aware_estimated_cost_usd": float(cost),
                        }),
                    ))
                    db.commit()
            except Exception as exc:
                print(f"[OpenAI Realtime] call log finalize failed: {exc}")
        db.close()
