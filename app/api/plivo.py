"""Signed Plivo Voice callbacks and Plivo XML answer flow."""

from __future__ import annotations

import asyncio
import json
import os
import threading
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from html import escape
import re

import pymysql
import requests
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.database.db import get_db
from app.services import business_hours_service, call_log_service, phone_number_service, transfer_service, ivr_service
from app.services.ivr_prompt_audio import ensure_prompt_audio
from app.services.transfer_prompt_audio import confirmation_audio_path, fallback_audio_path
from app.services.inbound_prompt_audio import unconfigured_audio_path, closed_audio_path
from app.services.language_prompt_audio import (
    language_prompt_tts_payload,
    normalize_language_prompt_wav,
)
from app.services.plivo_stream import build_answer_xml, build_language_prompt_xml, build_ivr_prompt_xml, build_direct_dial_xml, stream_token
from app.services.telephony import get_telephony_provider
from app.services.telephony.status import map_plivo_status

router = APIRouter(prefix="/api/plivo", tags=["Plivo"])

TERMINAL = {"completed", "busy", "no-answer", "canceled", "failed"}

_LANGUAGE_PROMPT_TEXT = "For English, press 1. தமிழுக்கு, இரண்டை அழுத்தவும்."
_LANGUAGE_PROMPT_PATH = (
    Path(__file__).resolve().parents[2] / "static" / "language_prompt_v2.wav"
)


def _ensure_language_prompt_audio() -> Path:
    """Render the bilingual DTMF-menu prompt once via OpenAI TTS and cache it on disk.

    Plivo's own <Speak> engine has no Tamil voice, so this clip is played
    back with <Play> instead of relying on provider-native TTS.
    """
    if _LANGUAGE_PROMPT_PATH.exists() and _LANGUAGE_PROMPT_PATH.stat().st_size > 0:
        return _LANGUAGE_PROMPT_PATH
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured; cannot render language prompt audio")
    response = requests.post(
        "https://api.openai.com/v1/audio/speech",
        headers={"Authorization": f"Bearer {api_key}"},
        json=language_prompt_tts_payload(_LANGUAGE_PROMPT_TEXT),
        timeout=30,
    )
    response.raise_for_status()
    _LANGUAGE_PROMPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _LANGUAGE_PROMPT_PATH.write_bytes(
        normalize_language_prompt_wav(response.content)
    )
    return _LANGUAGE_PROMPT_PATH


@router.get("/language-prompt.mp3", include_in_schema=False)
@router.get("/language-prompt-v2.wav")
async def language_prompt_audio() -> Response:
    path = await asyncio.to_thread(_ensure_language_prompt_audio)
    return Response(path.read_bytes(), media_type="audio/wav")


def _callback_url(request: Request) -> str:
    base = (os.getenv("WEBHOOK_BASE_URL") or "").strip().rstrip("/")
    if base:
        query = f"?{request.url.query}" if request.url.query else ""
        return f"{base}{request.url.path}{query}"
    return str(request.url)


def _organization_id_for_correlation(db: Any, correlation_id: str | None) -> int | None:
    """Resolve which tenant a webhook belongs to before validating its signature.

    Each webhook is signed with the Plivo account that placed the call. If a
    tenant has its own stored Plivo credentials, its callbacks must be
    validated against that tenant's signing key, not the shared .env one.
    """
    if not correlation_id:
        return None
    cursor = db.cursor()
    cursor.execute(
        "SELECT organization_id FROM call_logs WHERE correlation_id=%s", (correlation_id,)
    )
    row = cursor.fetchone()
    return int(row["organization_id"]) if row and row.get("organization_id") else None


async def _signed_form(request: Request, db: Any = None) -> dict[str, Any]:
    form = (
        dict(await request.form())
        if request.method.upper() == "POST"
        else dict(request.query_params)
    )
    validate = (os.getenv("PLIVO_VALIDATE_SIGNATURES") or "true").lower() in {
        "1", "true", "yes", "on",
    }
    dev = (os.getenv("ENVIRONMENT") or "development").lower() == "development"
    if validate or not dev:
        organization_id = (
            _organization_id_for_correlation(db, form.get("correlation_id") or request.query_params.get("correlation_id"))
            if db is not None else None
        )
        if not organization_id and db is not None:
            dialed_to = form.get("To") or request.query_params.get("To")
            if dialed_to:
                route = phone_number_service.get_active_route_for_number(db, str(dialed_to))
                if route and route.get("organization_id"):
                    organization_id = int(route["organization_id"])
        provider = get_telephony_provider(db, organization_id) if organization_id else get_telephony_provider()
        valid = provider.validate_callback(
            method=request.method,
            url=_callback_url(request),
            nonce=request.headers.get("X-Plivo-Signature-V3-Nonce", ""),
            signature=request.headers.get("X-Plivo-Signature-V3", ""),
            params=form,
        )
        if not valid:
            raise HTTPException(status_code=403, detail="Invalid Plivo V3 signature")
    return form


def _claim_event(
    db: pymysql.Connection, event_type: str, event_key: str, call_log_id: int | None,
    payload: dict[str, Any],
) -> bool:
    safe_payload = {
        key: payload.get(key)
        for key in (
            "Event", "CallStatus", "HangupCause", "HangupCauseName",
            "CallUUID", "RequestUUID", "StreamID", "RecordingID",
            "Duration", "BillDuration", "RecordingDuration", "Timestamp",
            "Direction", "StatusReason",
        )
        if payload.get(key) is not None
    }
    cursor = db.cursor()
    cursor.execute(
        """INSERT IGNORE INTO provider_callback_events
           (provider,event_type,event_key,call_log_id,payload)
           VALUES ('plivo',%s,%s,%s,%s)""",
        (event_type, event_key, call_log_id, json.dumps(safe_payload, ensure_ascii=False)),
    )
    db.commit()
    return cursor.rowcount == 1


def _bind(db: pymysql.Connection, correlation_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
    call_id = data.get("CallUUID") or data.get("call_uuid")
    request_id = data.get("RequestUUID") or data.get("request_uuid")
    if call_id and correlation_id:
        return call_log_service.bind_provider_call(
            db, correlation_id, str(call_id), str(data.get("CallStatus") or "")
        )
    if call_id:
        return call_log_service.get_call_log_by_sid(db, str(call_id))
    if request_id:
        return call_log_service.get_call_log_by_sid(db, str(request_id))
    return None


@router.api_route("/inbound", methods=["GET", "POST"])
async def inbound(
    request: Request, db: pymysql.Connection = Depends(get_db),
) -> Response:
    """Map an inbound Plivo number call into the same CRM and Realtime flow.

    The tenant is resolved from the dialed DID (Plivo's ``To`` field) via the
    ``phone_numbers`` table, so each business's own number routes to its own
    organization/campaign instead of everyone sharing one global campaign.
    """
    data = await _signed_form(request, db)
    base = (os.getenv("WEBHOOK_BASE_URL") or str(request.base_url)).strip().rstrip("/")
    dialed_number = str(data.get("To") or "").strip()
    route = phone_number_service.get_active_route_for_number(db, dialed_number)
    if not route:
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?><Response>'
            f'<Play>{escape(base + "/api/plivo/inbound-unconfigured.wav", quote=False)}</Play><Hangup/>'
            "</Response>"
        )
        return Response(xml, media_type="application/xml", status_code=503)

    organization_id = int(route["organization_id"])
    campaign_id = int(route["campaign_id"])

    hours_status = business_hours_service.is_open_now(db, organization_id)
    if not hours_status["is_open"]:
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?><Response>'
            f'<Play>{escape(base + "/api/plivo/inbound-closed.wav", quote=False)}</Play><Hangup/>'
            "</Response>"
        )
        return Response(xml, media_type="application/xml")

    cursor = db.cursor()
    phone = str(data.get("From") or "").strip()
    digits = re.sub(r"\D", "", phone)
    cursor.execute(
        """SELECT id FROM customers
           WHERE organization_id=%s
             AND REPLACE(REPLACE(REPLACE(phone,'+',''),' ',''),'-','')=%s
           ORDER BY id DESC LIMIT 1""",
        (organization_id, digits),
    )
    customer = cursor.fetchone()
    if customer:
        customer_id = int(customer["id"])
    else:
        email = f"inbound_{digits or os.urandom(6).hex()}@phone.local"
        language = (os.getenv("PLIVO_INBOUND_LANGUAGE") or "tamil").strip().lower()
        if language not in {"english", "tamil"}:
            language = "tamil"
        cursor.execute(
            """INSERT INTO customers(organization_id,name,email,phone,language)
               VALUES (%s,'Inbound caller',%s,%s,%s)""",
            (organization_id, email, phone or None, language),
        )
        db.commit()
        customer_id = int(cursor.lastrowid)

    call_id = str(data.get("CallUUID") or "")
    correlation_id = f"in_{call_id or os.urandom(16).hex()}"
    existing = call_log_service.get_call_log_by_sid(db, call_id) if call_id else None
    if not existing:
        log = call_log_service.create_call_log(
            db, organization_id, customer_id, campaign_id,
            call_id or correlation_id, "in-progress",
            provider="plivo", provider_call_id=call_id or None,
            provider_request_id=str(data.get("RequestUUID") or "") or None,
            correlation_id=correlation_id,
        )
        cursor.execute(
            """UPDATE call_logs SET call_direction='inbound',
               answered_at=COALESCE(answered_at,NOW()) WHERE id=%s""",
            (log["id"],),
        )
        db.commit()
    else:
        correlation_id = existing.get("correlation_id") or correlation_id

    base = (os.getenv("WEBHOOK_BASE_URL") or str(request.base_url)).strip().rstrip("/")
    redirect_query = urlencode({
        "customer_id": customer_id,
        "campaign_id": campaign_id,
        "correlation_id": correlation_id,
    })
    redirect_url = f"{base}/api/plivo/answer?{redirect_query}"
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?><Response>'
        f'<Redirect method="POST">{escape(redirect_url, quote=False)}</Redirect>'
        "</Response>"
    )
    return Response(xml, media_type="application/xml")


def _stream_urls(
    request: Request, customer_id: int, campaign_id: int, correlation_id: str,
) -> tuple[str, str, str]:
    base = (os.getenv("WEBHOOK_BASE_URL") or str(request.base_url)).strip().rstrip("/")
    ws_base = (os.getenv("PLIVO_STREAM_BASE_URL") or base).replace("https://", "wss://").replace("http://", "ws://")
    token = stream_token(customer_id, campaign_id, correlation_id)
    query = urlencode({
        "customer_id": customer_id,
        "campaign_id": campaign_id,
        "correlation_id": correlation_id,
        "token": token,
    })
    stream_url = f"{ws_base}/ws/plivo/media?{query}"
    record_url = f"{base}/api/plivo/recording?correlation_id={correlation_id}"
    stream_status_url = f"{base}/api/plivo/stream-status?correlation_id={correlation_id}"
    return stream_url, record_url, stream_status_url


@router.api_route("/answer", methods=["GET", "POST"])
async def answer(
    request: Request, customer_id: int, campaign_id: int, correlation_id: str,
    db: pymysql.Connection = Depends(get_db),
) -> Response:
    data = await _signed_form(request, db)
    log = _bind(db, correlation_id, data)
    call_id = str(data.get("CallUUID") or (log or {}).get("provider_call_id") or "")
    base = (os.getenv("WEBHOOK_BASE_URL") or str(request.base_url)).strip().rstrip("/")
    stream_url, record_url, stream_status_url = _stream_urls(
        request, customer_id, campaign_id, correlation_id
    )
    action_query = urlencode({
        "customer_id": customer_id, "campaign_id": campaign_id, "correlation_id": correlation_id,
    })
    action_url = f"{base}/api/plivo/language-select?{action_query}"
    play_url = f"{base}/api/plivo/language-prompt-v2.wav"
    # No provider <Speak>: the DTMF menu is a pre-rendered clip, and OpenAI
    # Realtime owns the single greeting/voice once the stream connects.
    xml = build_language_prompt_xml(action_url, play_url, stream_url, record_url, stream_status_url)
    if call_id:
        call_log_service.update_call_log_status(db, call_id, "in-progress")
    return Response(xml, media_type="application/xml")


@router.post("/language-select")
async def language_select(
    request: Request, customer_id: int, campaign_id: int, correlation_id: str,
    db: pymysql.Connection = Depends(get_db),
) -> Response:
    """Handle the customer's English/Tamil keypress and start the AI stream."""
    data = await _signed_form(request, db)
    log = _bind(db, correlation_id, data)
    call_id = str(data.get("CallUUID") or (log or {}).get("provider_call_id") or "")
    digit = str(data.get("Digits") or "").strip()
    language = {"1": "english", "2": "tamil"}.get(digit)
    if language and log:
        call_log_service.update_selected_language(
            db,
            int(log["id"]),
            int(log["organization_id"]),
            customer_id,
            language,
        )
    stream_url, record_url, stream_status_url = _stream_urls(
        request, customer_id, campaign_id, correlation_id
    )
    # An organization's IVR menu (labels, and each option's AI-campaign or
    # human destination) now drives the AI's own spoken routing question
    # inside the Realtime bridge itself, instead of a separate pre-recorded
    # Plivo menu -- so every call goes straight to the AI stream here, and
    # the AI decides whether to ask a routing question based on that same
    # IVR configuration.
    xml = build_answer_xml(stream_url, record_url, stream_status_url)
    if call_id:
        call_log_service.update_call_log_status(db, call_id, "in-progress")
    return Response(xml, media_type="application/xml")


@router.get("/ivr-prompt.wav", include_in_schema=False)
async def ivr_prompt_audio(settings_id: int, token: str, language: str, db: pymysql.Connection = Depends(get_db)) -> Response:
    """Serve only the current short menu clip behind a random settings token."""
    if language not in {"english", "tamil"}:
        raise HTTPException(status_code=404, detail="Prompt not found")
    settings = ivr_service.validate_audio_token(db, settings_id, token)
    if not settings:
        raise HTTPException(status_code=404, detail="Prompt not found")
    menu = ivr_service.get_live_menu(db, int(settings["organization_id"]), language)
    if not menu or int(menu["id"]) != settings_id:
        raise HTTPException(status_code=404, detail="Prompt not found")
    try:
        path = await asyncio.to_thread(ensure_prompt_audio, menu["prompt"])
        return Response(path.read_bytes(), media_type="audio/wav", headers={"Cache-Control": "private, max-age=86400"})
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"IVR prompt unavailable: {type(exc).__name__}") from exc


@router.post("/ivr-select")
async def ivr_select(
    request: Request, customer_id: int, campaign_id: int, correlation_id: str,
    db: pymysql.Connection = Depends(get_db),
) -> Response:
    data = await _signed_form(request, db)
    log = _bind(db, correlation_id, data)
    routed = None
    if log:
        routed = ivr_service.route_selection(
            db, organization_id=int(log["organization_id"]), call_log_id=int(log["id"]),
            digit=str(data.get("Digits") or "").strip(),
            speech_text=str(data.get("SpeechResult") or "").strip(),
        )
    if routed and routed.get("route_type") == "human" and (routed.get("destination_phones") or routed.get("destination_phone")):
        base = (os.getenv("WEBHOOK_BASE_URL") or str(request.base_url)).strip().rstrip("/")
        action_url = f"{base}/api/plivo/ivr-dial-action?{urlencode({'customer_id': customer_id, 'campaign_id': campaign_id, 'correlation_id': correlation_id})}"
        confirm_url = f"{base}/api/plivo/transfer-confirm.wav"
        dial_phones = routed.get("destination_phones") or str(routed["destination_phone"])
        xml = build_direct_dial_xml(action_url, confirm_url, dial_phones)
        return Response(xml, media_type="application/xml")
    selected_campaign_id = int(routed["campaign_id"]) if routed and routed.get("campaign_id") else campaign_id
    stream_url, record_url, stream_status_url = _stream_urls(
        request, customer_id, selected_campaign_id, correlation_id
    )
    return Response(build_answer_xml(stream_url, record_url, stream_status_url), media_type="application/xml")


@router.post("/ivr-dial-action")
async def ivr_dial_action(
    request: Request, customer_id: int, campaign_id: int, correlation_id: str,
    db: pymysql.Connection = Depends(get_db),
) -> Response:
    """Handle the outcome of an IVR option that dialed a human directly.

    On no-answer/busy/failed, this mirrors the existing human-transfer
    fallback exactly: queue a callback task and play an apology instead of
    silently dropping the caller or falling back to the AI (the AI is
    intentionally not part of this route at all).
    """
    data = await _signed_form(request, db)
    log = _bind(db, correlation_id, data)
    dial_status = str(data.get("DialStatus") or "").strip().lower()
    if log and dial_status not in {"completed", "answer", "answered"}:
        try:
            cursor = db.cursor()
            cursor.execute(
                "UPDATE call_logs SET followup_required=TRUE WHERE id=%s AND organization_id=%s",
                (log["id"], log["organization_id"]),
            )
            db.commit()
            from app.services import callback_service
            callback_service.ensure_for_call(
                db, organization_id=int(log["organization_id"]), call_log_id=int(log["id"]),
                source="ivr_direct_dial_no_answer",
            )
        except Exception as exc:
            print(f"[ivr_dial_action] Callback fallback failed: {type(exc).__name__}")
        base = (os.getenv("WEBHOOK_BASE_URL") or str(request.base_url)).strip().rstrip("/")
        xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Play>{escape(base + "/api/plivo/transfer-fallback.wav", quote=False)}</Play><Hangup/></Response>'
        return Response(xml, media_type="application/xml")
    return Response('<?xml version="1.0" encoding="UTF-8"?><Response><Hangup/></Response>', media_type="application/xml")


@router.api_route("/transfer-answer", methods=["GET", "POST"])
async def transfer_answer(
    request: Request, transfer_id: int, correlation_id: str,
    db: pymysql.Connection = Depends(get_db),
) -> Response:
    """Replace the AI stream with a confirmed human destination."""
    print(f"[transfer-answer] Plivo fetched this webhook | transfer_id={transfer_id}")
    await _signed_form(request, db)
    transfer = transfer_service.get_transfer_for_webhook(db, transfer_id, correlation_id)
    if not transfer or transfer["status"] in transfer_service.FINAL_TRANSFER_STATUSES:
        print(f"[transfer-answer] No active transfer found | transfer_id={transfer_id} transfer={transfer}")
        raise HTTPException(status_code=404, detail="Active transfer not found")
    phones = transfer_service.get_transfer_phone_numbers(
        db, int(transfer["organization_id"]), int(transfer["destination_id"]),
    )
    if not phones:
        phones = [str(transfer["destination_phone"])]
    print(f"[transfer-answer] Dialing destination(s) {phones} | transfer_id={transfer_id}")
    base = (os.getenv("WEBHOOK_BASE_URL") or str(request.base_url)).strip().rstrip("/")
    query = urlencode({"transfer_id": transfer_id, "correlation_id": correlation_id})
    action_url = escape(f"{base}/api/plivo/transfer-action?{query}", quote=True)
    callback_url = escape(f"{base}/api/plivo/transfer-callback?{query}", quote=True)
    confirm_url = escape(f"{base}/api/plivo/transfer-confirm?{query}", quote=True)
    number_tags = "".join(f"<Number>{escape(num, quote=False)}</Number>" for num in phones)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?><Response>'
        f'<Dial action="{action_url}" method="POST" timeout="25" timeLimit="14400" '
        f'callbackUrl="{callback_url}" callbackMethod="POST" '
        f'confirmSound="{confirm_url}" confirmKey="1" confirmTimeout="10">'
        f'{number_tags}</Dial></Response>'
    )
    return Response(xml, media_type="application/xml")


@router.api_route("/transfer-confirm", methods=["GET", "POST"])
async def transfer_confirm(
    request: Request, transfer_id: int, correlation_id: str,
    db: pymysql.Connection = Depends(get_db),
) -> Response:
    await _signed_form(request, db)
    if not transfer_service.get_transfer_for_webhook(db, transfer_id, correlation_id):
        raise HTTPException(status_code=404, detail="Transfer not found")
    base = (os.getenv("WEBHOOK_BASE_URL") or str(request.base_url)).strip().rstrip("/")
    xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Play>{escape(base + "/api/plivo/transfer-confirm.wav", quote=False)}</Play></Response>'
    return Response(xml, media_type="application/xml")


@router.get("/transfer-confirm.wav", include_in_schema=False)
async def transfer_confirmation_audio() -> Response:
    path = await asyncio.to_thread(confirmation_audio_path)
    return Response(path.read_bytes(), media_type="audio/wav", headers={"Cache-Control": "public, max-age=86400"})


@router.get("/transfer-fallback.wav", include_in_schema=False)
async def transfer_fallback_audio() -> Response:
    path = await asyncio.to_thread(fallback_audio_path)
    return Response(path.read_bytes(), media_type="audio/wav", headers={"Cache-Control": "public, max-age=86400"})


@router.get("/inbound-unconfigured.wav", include_in_schema=False)
async def inbound_unconfigured_audio() -> Response:
    path = await asyncio.to_thread(unconfigured_audio_path)
    return Response(path.read_bytes(), media_type="audio/wav", headers={"Cache-Control": "public, max-age=86400"})


@router.get("/inbound-closed.wav", include_in_schema=False)
async def inbound_closed_audio() -> Response:
    path = await asyncio.to_thread(closed_audio_path)
    return Response(path.read_bytes(), media_type="audio/wav", headers={"Cache-Control": "public, max-age=86400"})


@router.post("/transfer-callback")
async def transfer_callback(
    request: Request, transfer_id: int, correlation_id: str,
    db: pymysql.Connection = Depends(get_db),
) -> dict[str, str]:
    data = await _signed_form(request, db)
    transfer = transfer_service.apply_dial_event(
        db, transfer_id=transfer_id, correlation_id=correlation_id,
        data=data, final=False,
    )
    if not transfer:
        raise HTTPException(status_code=404, detail="Transfer not found")
    return {"status": "ok"}


@router.post("/transfer-update-callback")
async def transfer_update_callback(
    request: Request, transfer_id: int, correlation_id: str,
    db: pymysql.Connection = Depends(get_db),
) -> dict[str, str]:
    """Plivo's report on whether the aleg redirect for a transfer actually
    ran, not just whether the REST request to start it was accepted. This
    is the only way to see a redirect that silently never executed.
    """
    data = await _signed_form(request, db)
    print(f"[transfer-update-callback] transfer_id={transfer_id} data={data}")
    return {"status": "ok"}


@router.post("/transfer-action")
async def transfer_action(
    request: Request, transfer_id: int, correlation_id: str,
    db: pymysql.Connection = Depends(get_db),
) -> Response:
    data = await _signed_form(request, db)
    print(
        f"[transfer-action] DialStatus={data.get('DialStatus')!r} "
        f"transfer_id={transfer_id}"
    )
    transfer = transfer_service.apply_dial_event(
        db, transfer_id=transfer_id, correlation_id=correlation_id,
        data=data, final=True,
    )
    if not transfer:
        raise HTTPException(status_code=404, detail="Transfer not found")
    print(f"[transfer-action] transfer now status={transfer['status']} | transfer_id={transfer_id}")
    if transfer["status"] in {"failed", "cancelled"}:
        try:
            from app.services import callback_service
            cursor = db.cursor()
            cursor.execute(
                "UPDATE call_logs SET followup_required=TRUE WHERE id=%s AND organization_id=%s",
                (transfer["call_log_id"], transfer["organization_id"]),
            )
            db.commit()
            callback_service.ensure_for_call(
                db,
                organization_id=int(transfer["organization_id"]),
                call_log_id=int(transfer["call_log_id"]),
                source="transfer_fallback",
            )
        except Exception as exc:
            print(f"[transfer] Callback fallback failed: {type(exc).__name__}")
        base = (os.getenv("WEBHOOK_BASE_URL") or str(request.base_url)).strip().rstrip("/")
        xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Play>{escape(base + "/api/plivo/transfer-fallback.wav", quote=False)}</Play><Hangup/></Response>'
    else:
        if transfer["status"] == "completed":
            try:
                cursor = db.cursor()
                cursor.execute(
                    "SELECT provider_recording_id FROM call_logs WHERE id=%s AND organization_id=%s",
                    (transfer["call_log_id"], transfer["organization_id"]),
                )
                log_row = cursor.fetchone()
                if log_row and log_row.get("provider_recording_id"):
                    _trigger_transferred_call_reanalysis(
                        int(transfer["organization_id"]), int(transfer["call_log_id"])
                    )
            except Exception as trigger_exc:
                print(f"[transfer-action] Reanalysis trigger failed: {type(trigger_exc).__name__}: {trigger_exc}")
        xml = '<?xml version="1.0" encoding="UTF-8"?><Response><Hangup/></Response>'
    return Response(xml, media_type="application/xml")


@router.post("/ring")
async def ring(
    request: Request, correlation_id: str, db: pymysql.Connection = Depends(get_db),
) -> dict[str, str]:
    data = await _signed_form(request, db)
    log = _bind(db, correlation_id, data)
    call_id = str(data.get("CallUUID") or "")
    key = call_id or str(data.get("RequestUUID") or correlation_id)
    if log and _claim_event(db, "ring", key, log["id"], data):
        call_log_service.update_call_log_status(db, key, "ringing")
    return {"status": "ok"}


@router.post("/hangup")
async def hangup(
    request: Request, correlation_id: str, db: pymysql.Connection = Depends(get_db),
) -> dict[str, str]:
    data = await _signed_form(request, db)
    log = _bind(db, correlation_id, data)
    call_id = str(data.get("CallUUID") or (log or {}).get("provider_call_id") or "")
    status = map_plivo_status(
        data.get("CallStatus") or data.get("DialStatus") or "completed",
        data.get("HangupCause") or data.get("HangupCauseName"),
    )
    try:
        duration = int(data.get("BillDuration") or data.get("Duration") or 0)
    except (TypeError, ValueError):
        duration = 0
    if log and call_id:
        claimed = _claim_event(db, "hangup", call_id, log["id"], data)
        if claimed:
            await asyncio.to_thread(
                call_log_service.finalize_call_log, db, call_id, status, duration
            )
        # CDR data may lag the first hangup callback. Retried callbacks are
        # allowed to fill billing fields without repeating CRM side effects.
        try:
            hangup_provider = get_telephony_provider(db, log.get("organization_id"))
            details = await asyncio.to_thread(hangup_provider.get_call, call_id)
            cursor = db.cursor()
            cursor.execute(
                """UPDATE call_logs SET estimated_telephony_cost_usd=%s,
                   provider_bill_duration_seconds=%s WHERE id=%s""",
                (details.cost_usd, details.billed_duration_seconds, log["id"]),
            )
            db.commit()
        except Exception as exc:
            print(f"[Plivo] CDR not ready call={call_id}: {type(exc).__name__}")
    return {"status": "ok"}


@router.post("/recording")
async def recording(
    request: Request, correlation_id: str, db: pymysql.Connection = Depends(get_db),
) -> dict[str, str]:
    data = await _signed_form(request, db)
    log = _bind(db, correlation_id, data)
    recording_id = str(data.get("RecordingID") or "")
    if log and recording_id and _claim_event(
        db, "recording", recording_id, log["id"], data
    ):
        cursor = db.cursor()
        cursor.execute(
            """UPDATE call_logs SET provider_recording_id=%s, recording_sid=%s,
               recording_status='completed', recording_duration_seconds=%s,
               recording_channels=2 WHERE id=%s""",
            (
                recording_id,
                recording_id,
                int(float(data.get("RecordingDuration") or 0)),
                log["id"],
            ),
        )
        db.commit()
        _trigger_transferred_call_reanalysis(int(log["organization_id"]), int(log["id"]))
    return {"status": "ok"}


def _trigger_transferred_call_reanalysis(organization_id: int, call_log_id: int) -> None:
    """A call transferred to a human is only fully qualified once its
    recording (covering the human conversation too) is transcribed and
    re-scored -- runs off the request thread since it involves an
    OpenAI transcription call plus a Plivo recording download.
    """
    def run() -> None:
        from app.database.db import get_db_connection
        from app.services import call_recording_analysis
        conn = get_db_connection()
        try:
            call_recording_analysis.reanalyze_transferred_call(conn, organization_id, call_log_id)
        except Exception as exc:
            print(f"[recording] Reanalysis thread failed for call {call_log_id}: {type(exc).__name__}: {exc}")
        finally:
            conn.close()

    threading.Thread(target=run, daemon=True).start()


@router.post("/stream-status")
async def stream_status(
    request: Request, correlation_id: str, db: pymysql.Connection = Depends(get_db),
) -> dict[str, str]:
    data = await _signed_form(request, db)
    log = _bind(db, correlation_id, data)
    stream_id = str(data.get("StreamID") or "")
    event = str(data.get("Event") or "unknown").lower()
    if log and stream_id and _claim_event(
        db, f"stream:{event}", f"{stream_id}:{event}", log["id"], data
    ):
        cursor = db.cursor()
        cursor.execute(
            """UPDATE call_logs SET provider_stream_id=%s, stream_sid=%s,
               stream_status=%s,
               failure_reason=CASE WHEN %s IN ('failed','droppedstream')
                 THEN COALESCE(%s,failure_reason) ELSE failure_reason END
               WHERE id=%s""",
            (
                stream_id, stream_id, event, event,
                data.get("StatusReason") or data.get("Error"), log["id"],
            ),
        )
        db.commit()
    return {"status": "ok"}


@router.post("/fallback")
async def fallback(
    request: Request, correlation_id: str, db: pymysql.Connection = Depends(get_db),
) -> Response:
    """Plivo lands here when it could not reach /answer at all (e.g. a dead
    tunnel at the moment of pickup). Without this, the call_logs row and the
    campaign sheet row would be stuck at a non-terminal status forever,
    blocking this lead from ever being retried and stalling the queue.
    """
    data = await _signed_form(request, db)
    log = _bind(db, correlation_id, data)
    call_id = str(data.get("CallUUID") or (log or {}).get("provider_call_id") or "")
    if log and call_id:
        claimed = _claim_event(db, "fallback", call_id, log["id"], data)
        if claimed:
            updated = await asyncio.to_thread(
                call_log_service.finalize_call_log, db, call_id, "failed", 0,
            )
            record = updated or log
            sheet_url = record.get("sheet_url")
            sheet_row = record.get("sheet_row")
            campaign_id = record.get("campaign_id")
            if sheet_url and sheet_row and campaign_id:
                await asyncio.to_thread(
                    call_log_service.update_feedback_and_trigger_next,
                    sheet_url,
                    int(sheet_row),
                    {
                        "status": "failed",
                        "summary": "Call could not be connected (answer webhook unreachable).",
                    },
                    campaign_id,
                )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?><Response>'
        "<Speak>Sorry, the voice assistant is temporarily unavailable. "
        "Our counsellor will call you back.</Speak><Hangup/></Response>"
    )
    return Response(xml, media_type="application/xml")


@router.post("/compliance-webhook")
async def compliance_webhook(
    request: Request, db: pymysql.Connection = Depends(get_db),
) -> dict[str, str]:
    """Plivo calls this when a submitted KYC compliance application is
    approved or rejected (see plivo_provisioning_service.submit_compliance_application).

    KNOWN GAP: this endpoint does not validate a Plivo signature. The Voice
    V3 signing scheme other handlers in this file use is specific to voice
    callbacks; the Compliance API's webhook authentication mechanism has not
    been confirmed yet. Until it is, this accepts any POST body shaped like
    a compliance callback, which is a real (if narrow) spoofing surface: at
    worst, someone could falsely mark an application as approved/rejected in
    our own tracking table. It cannot be used to place calls, access data,
    or bypass Plivo's own approval, since Plivo alone controls when a number
    can actually be bought against an application. Track down the real
    authentication mechanism before this handles anything higher-stakes.
    """
    from app.services import plivo_provisioning_service

    try:
        payload = await request.json()
    except Exception:
        payload = dict(await request.form())
    plivo_provisioning_service.handle_compliance_webhook(db, payload)
    return {"status": "ok"}
