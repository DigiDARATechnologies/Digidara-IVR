"""Configurable call-duration enforcement and post-call anomaly signals."""

from __future__ import annotations

import json
import os
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from app.services.usage_cost_service import provider_cost_summary


DEFAULT_MAX_DURATION_SECONDS = 900
DEFAULT_TOTAL_COST_ALERT_INR = Decimal("50")
DEFAULT_COST_PER_MINUTE_ALERT_INR = Decimal("8")
DEFAULT_TURNS_PER_MINUTE_ALERT = Decimal("8")
DEFAULT_INTERRUPTION_ALERT_COUNT = 5
DEFAULT_FALSE_TURN_ALERT_COUNT = 3


def _bounded_int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    return min(max(value, minimum), maximum)


def _positive_decimal_env(name: str, default: Decimal) -> Decimal:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"{name} must be a decimal number") from exc
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


def call_duration_limit_seconds() -> int:
    """Return the provider-enforced limit, bounded to Plivo's supported range."""
    return _bounded_int_env(
        "CALL_MAX_DURATION_SECONDS", DEFAULT_MAX_DURATION_SECONDS, 60, 86400
    )


def guardrail_thresholds() -> dict[str, float | int]:
    return {
        "maximum_duration_seconds": call_duration_limit_seconds(),
        "estimated_total_cost_inr": float(_positive_decimal_env(
            "CALL_ESTIMATED_COST_ALERT_INR", DEFAULT_TOTAL_COST_ALERT_INR
        )),
        "estimated_cost_per_minute_inr": float(_positive_decimal_env(
            "CALL_ESTIMATED_COST_PER_MINUTE_ALERT_INR",
            DEFAULT_COST_PER_MINUTE_ALERT_INR,
        )),
        "turns_per_minute": float(_positive_decimal_env(
            "CALL_TURNS_PER_MINUTE_ALERT", DEFAULT_TURNS_PER_MINUTE_ALERT
        )),
        "interruption_count": _bounded_int_env(
            "CALL_INTERRUPTION_ALERT_COUNT", DEFAULT_INTERRUPTION_ALERT_COUNT, 1, 1000
        ),
        "false_turn_count": _bounded_int_env(
            "CALL_FALSE_TURN_ALERT_COUNT", DEFAULT_FALSE_TURN_ALERT_COUNT, 1, 1000
        ),
    }


def _number(value: Any) -> Decimal:
    try:
        return max(Decimal(str(value or 0)), Decimal("0"))
    except InvalidOperation:
        return Decimal("0")


def _stored_duration_limit(call: Mapping[str, Any]) -> int:
    metadata = call.get("provider_metadata")
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except (TypeError, ValueError):
            metadata = {}
    if isinstance(metadata, Mapping):
        stored = metadata.get("time_limit_seconds")
        try:
            if stored is not None:
                return min(max(int(stored), 60), 86400)
        except (TypeError, ValueError):
            pass
    return call_duration_limit_seconds()


def evaluate_call_guardrails(call: Mapping[str, Any]) -> dict[str, Any]:
    """Derive stable review metrics and reason codes from a call-log row."""
    duration_seconds = _number(call.get("duration"))
    duration_minutes = duration_seconds / Decimal("60")
    turns = _number(call.get("total_turns"))
    interruptions = _number(call.get("interruption_count"))
    false_turns = _number(call.get("false_turn_count"))
    costs = provider_cost_summary(
        call.get("estimated_openai_cost_usd"),
        call.get("estimated_telephony_cost_usd")
        if call.get("estimated_telephony_cost_usd") is not None
        else call.get("estimated_twilio_cost_usd"),
    )
    total_inr = Decimal(str(costs["total_estimated_inr"]))
    turns_per_minute = turns / duration_minutes if duration_minutes else Decimal("0")
    interruptions_per_minute = (
        interruptions / duration_minutes if duration_minutes else Decimal("0")
    )
    cost_per_minute = total_inr / duration_minutes if duration_minutes else Decimal("0")
    thresholds = guardrail_thresholds()
    duration_limit = _stored_duration_limit(call)
    reasons: list[str] = []

    if duration_seconds >= duration_limit:
        reasons.append("maximum_duration_reached")
    if total_inr >= Decimal(str(thresholds["estimated_total_cost_inr"])):
        reasons.append("high_estimated_total_cost")
    if duration_minutes and cost_per_minute >= Decimal(
        str(thresholds["estimated_cost_per_minute_inr"])
    ):
        reasons.append("high_estimated_cost_per_minute")
    if duration_minutes and turns_per_minute >= Decimal(str(thresholds["turns_per_minute"])):
        reasons.append("high_turn_rate")
    if interruptions >= Decimal(str(thresholds["interruption_count"])):
        reasons.append("repeated_interruptions")
    if false_turns >= Decimal(str(thresholds["false_turn_count"])):
        reasons.append("repeated_false_turns")

    return {
        "duration_minutes": round(float(duration_minutes), 2),
        "turns_per_minute": round(float(turns_per_minute), 2),
        "interruptions_per_minute": round(float(interruptions_per_minute), 2),
        "estimated_total_inr": float(total_inr),
        "estimated_cost_per_minute_inr": round(float(cost_per_minute), 2),
        "is_abnormal": bool(reasons),
        "abnormal_reasons": reasons,
        "call_duration_limit_seconds": duration_limit,
    }


def with_call_guardrails(call: Mapping[str, Any]) -> dict[str, Any]:
    enriched = dict(call)
    enriched.update(evaluate_call_guardrails(call))
    return enriched
