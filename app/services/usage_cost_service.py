"""Provider cost estimation and historical usage reconciliation."""

from __future__ import annotations

import json
import os
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping


COST_ESTIMATION_VERSION = "openai_realtime_cache_aware_v1"
ONE_MILLION = Decimal("1000000")


def _decimal_env(name: str, default: str) -> Decimal:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return Decimal(default)
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"{name} must be a decimal number") from exc


def _decimal_override(name: str, fallback_name: str, default: str) -> Decimal:
    """Read a specific override first, then a shared fallback rate."""
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return _decimal_env(fallback_name, default)
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"{name} must be a decimal number") from exc


def realtime_token_rates(model: str, language: str) -> dict[str, Decimal]:
    """Return official/default USD-per-million Realtime token rates."""
    if model == "gpt-realtime-2.1":
        defaults = {
            "audio_input": "32.0",
            "audio_cached_input": "0.40",
            "audio_output": "64.0",
            "text_input": "4.0",
            "text_cached_input": "0.40",
            "text_output": "24.0",
        }
    else:
        defaults = {
            "audio_input": "10.0",
            "audio_cached_input": "0.30",
            "audio_output": "20.0",
            "text_input": "0.60",
            "text_cached_input": "0.06",
            "text_output": "2.40",
        }
    env_names = {
        "audio_input": "OPENAI_AUDIO_INPUT_USD_PER_M",
        "audio_cached_input": "OPENAI_AUDIO_CACHED_INPUT_USD_PER_M",
        "audio_output": "OPENAI_AUDIO_OUTPUT_USD_PER_M",
        "text_input": "OPENAI_TEXT_INPUT_USD_PER_M",
        "text_cached_input": "OPENAI_TEXT_CACHED_INPUT_USD_PER_M",
        "text_output": "OPENAI_TEXT_OUTPUT_USD_PER_M",
    }
    tamil = language.strip().lower() == "tamil"
    rates: dict[str, Decimal] = {}
    for key, env_name in env_names.items():
        tamil_name = f"{env_name}_TAMIL"
        rates[key] = (
            _decimal_override(tamil_name, env_name, defaults[key])
            if tamil
            else _decimal_env(env_name, defaults[key])
        )
    return rates


def transcription_token_rates(
    transcription_model: str, language: str = "english",
) -> dict[str, Decimal]:
    if transcription_model == "gpt-4o-transcribe":
        defaults = {"audio_input": "6.0", "text_output": "10.0"}
    else:
        defaults = {"audio_input": "3.0", "text_output": "5.0"}
    tamil = language.strip().lower() == "tamil"
    rates = {}
    for key, env_name in {
        "audio_input": "OPENAI_TRANSCRIBE_AUDIO_INPUT_USD_PER_M",
        "text_output": "OPENAI_TRANSCRIBE_TEXT_OUTPUT_USD_PER_M",
    }.items():
        rates[key] = (
            _decimal_override(f"{env_name}_TAMIL", env_name, defaults[key])
            if tamil
            else _decimal_env(env_name, defaults[key])
        )
    return rates


def _token_count(usage: Mapping[str, Any], name: str) -> Decimal:
    try:
        return max(Decimal(str(usage.get(name) or 0)), Decimal("0"))
    except InvalidOperation as exc:
        raise ValueError(f"{name} must be a numeric token count") from exc


def estimate_openai_cost_usd(
    usage: Mapping[str, Any], model: str, language: str,
    transcription_model: str,
) -> Decimal:
    """Estimate cost while charging cached input at its discounted rate."""
    rates = realtime_token_rates(model, language)
    transcription_rates = transcription_token_rates(transcription_model, language)
    input_audio = _token_count(usage, "input_audio")
    input_text = _token_count(usage, "input_text")
    cached_audio = min(_token_count(usage, "cached_input_audio"), input_audio)
    cached_text = min(_token_count(usage, "cached_input_text"), input_text)
    uncached_audio = input_audio - cached_audio
    uncached_text = input_text - cached_text
    total = (
        uncached_audio * rates["audio_input"]
        + cached_audio * rates["audio_cached_input"]
        + _token_count(usage, "output_audio") * rates["audio_output"]
        + uncached_text * rates["text_input"]
        + cached_text * rates["text_cached_input"]
        + _token_count(usage, "output_text") * rates["text_output"]
        + _token_count(usage, "transcription_input_audio")
        * transcription_rates["audio_input"]
        + _token_count(usage, "transcription_output_text")
        * transcription_rates["text_output"]
    )
    return total / ONE_MILLION


def provider_cost_summary(openai_usd: Any, telephony_usd: Any) -> dict[str, float]:
    """Present OpenAI and Plivo costs with independent INR conversion rates."""
    openai = Decimal(str(openai_usd or 0))
    telephony = Decimal(str(telephony_usd or 0))
    openai_rate = _decimal_env("USD_TO_INR_RATE", "96.16")
    plivo_rate = _decimal_env("PLIVO_USD_TO_INR_RATE", "80.00")
    openai_inr = openai * openai_rate
    plivo_inr = telephony * plivo_rate
    return {
        "openai_estimated_usd": float(openai),
        "openai_estimated_inr": round(float(openai_inr), 2),
        "plivo_recorded_usd": float(telephony),
        "plivo_recorded_inr": round(float(plivo_inr), 2),
        "total_estimated_inr": round(float(openai_inr + plivo_inr), 2),
        "openai_usd_to_inr": float(openai_rate),
        "plivo_usd_to_inr": float(plivo_rate),
    }


def _usage_json(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _row_language(row: Mapping[str, Any]) -> str:
    tamil_signals = (
        str(row.get("turn_gate_profile") or ""),
        str(row.get("voice_style_profile") or ""),
    )
    if row.get("transcription_model") == "gpt-4o-transcribe" or any(
        "tamil" in signal.lower() for signal in tamil_signals
    ):
        return "tamil"
    return "english" if str(row.get("language") or "").lower() != "tamil" else "tamil"


def estimate_usage_row_cost_usd(row: Mapping[str, Any]) -> Decimal:
    usage_data = _usage_json(row.get("usage_data"))
    usage = {
        "input_audio": row.get("input_audio_tokens"),
        "output_audio": row.get("output_audio_tokens"),
        "input_text": row.get("input_text_tokens"),
        "output_text": row.get("output_text_tokens"),
        "cached_input_audio": row.get("cached_input_audio_tokens"),
        "cached_input_text": row.get("cached_input_text_tokens"),
        "transcription_input_audio": usage_data.get("transcription_input_audio"),
        "transcription_output_text": usage_data.get("transcription_output_text"),
    }
    return estimate_openai_cost_usd(
        usage,
        str(row.get("model_name") or row.get("realtime_model") or ""),
        _row_language(row),
        str(row.get("transcription_model") or "gpt-4o-mini-transcribe"),
    )


def backfill_openai_cost_estimates(db: Any) -> dict[str, Any]:
    """Recalculate stored estimates atomically from retained Realtime usage."""
    cursor = db.cursor()
    cursor.execute("""
        SELECT ru.id,ru.call_log_id,ru.model_name,ru.input_audio_tokens,
               ru.output_audio_tokens,ru.input_text_tokens,ru.output_text_tokens,
               ru.cached_input_audio_tokens,ru.cached_input_text_tokens,
               ru.estimated_cost_usd,ru.usage_data,l.language,
               l.transcription_model,l.voice_style_profile,l.turn_gate_profile
        FROM realtime_usage ru
        JOIN call_logs l ON l.id=ru.call_log_id
        ORDER BY ru.call_log_id,ru.id
    """)
    rows = cursor.fetchall()
    latest_by_call: dict[int, Decimal] = {}
    old_total = Decimal("0")
    new_total = Decimal("0")
    try:
        for row in rows:
            old_cost = Decimal(str(row.get("estimated_cost_usd") or 0))
            new_cost = estimate_usage_row_cost_usd(row)
            usage_data = _usage_json(row.get("usage_data"))
            usage_data.setdefault("legacy_estimated_cost_usd", float(old_cost))
            usage_data["cost_estimation_version"] = COST_ESTIMATION_VERSION
            usage_data["cache_aware_estimated_cost_usd"] = float(new_cost)
            cursor.execute(
                "UPDATE realtime_usage SET estimated_cost_usd=%s,usage_data=%s WHERE id=%s",
                (new_cost, json.dumps(usage_data), row["id"]),
            )
            latest_by_call[int(row["call_log_id"])] = new_cost
            old_total += old_cost
            new_total += new_cost
        for call_log_id, cost in latest_by_call.items():
            cursor.execute(
                "UPDATE call_logs SET estimated_openai_cost_usd=%s WHERE id=%s",
                (cost, call_log_id),
            )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {
        "usage_rows": len(rows),
        "call_logs": len(latest_by_call),
        "old_estimated_usd": old_total,
        "new_estimated_usd": new_total,
        "estimation_version": COST_ESTIMATION_VERSION,
    }
