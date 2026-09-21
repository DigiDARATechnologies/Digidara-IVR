"""Plivo implementation of the provider-neutral telephony contract."""

from __future__ import annotations

import os
import re
from typing import Any, Mapping

from .base import CallDetails, CreateCallResult, TransferCallResult


def _value(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


class PlivoProvider:
    name = "plivo"

    def __init__(
        self, auth_id: str | None = None, auth_token: str | None = None,
        from_number: str | None = None, client: Any = None,
    ) -> None:
        self.auth_id = (auth_id or os.getenv("PLIVO_AUTH_ID") or "").strip()
        self.auth_token = (auth_token or os.getenv("PLIVO_AUTH_TOKEN") or "").strip()
        raw_from_number = (from_number or os.getenv("PLIVO_FROM_NUMBER") or "").strip()
        # Plivo requires numeric caller IDs in E.164. Be tolerant of spaces and
        # display punctuation copied from the console, but always send E.164.
        self.from_number = (
            f"+{re.sub(r'[^0-9]', '', raw_from_number)}"
            if raw_from_number.startswith("+")
            else raw_from_number
        )
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                import plivo
            except ImportError as exc:
                raise RuntimeError(
                    "The Plivo SDK is not installed. Run pip install -r app/requirements.txt."
                ) from exc
            self._client = plivo.RestClient(self.auth_id, self.auth_token)
        return self._client

    def is_configured(self) -> bool:
        placeholders = {"", "your_plivo_auth_id", "your_plivo_auth_token", "your_plivo_number"}
        return (
            self.auth_id not in placeholders
            and self.auth_token not in placeholders
            and self.from_number not in placeholders
        )

    def create_call(
        self, *, to: str, answer_url: str, ring_url: str,
        hangup_url: str, fallback_url: str, time_limit_seconds: int,
    ) -> CreateCallResult:
        response = self.client.calls.create(
            from_=self.from_number,
            to_=to,
            answer_url=answer_url,
            answer_method="POST",
            ring_url=ring_url,
            ring_method="POST",
            hangup_url=hangup_url,
            hangup_method="POST",
            fallback_url=fallback_url,
            fallback_method="POST",
            time_limit=time_limit_seconds,
        )
        request_id = str(_value(response, "request_uuid") or "")
        if not request_id:
            raise RuntimeError("Plivo accepted no request UUID")
        return CreateCallResult(
            provider=self.name,
            request_id=request_id,
            metadata={"api_id": _value(response, "api_id"), "message": _value(response, "message")},
        )

    def terminate_call(self, *, call_id: str | None, request_id: str | None) -> None:
        if not call_id and not request_id:
            raise ValueError("A provider call ID or request ID is required")
        from plivo.exceptions import ResourceNotFoundError

        try:
            if call_id:
                self.client.calls.delete(call_id)
            else:
                self.client.calls.cancel(request_id)
        except ResourceNotFoundError:
            # Plivo already has no live call under this ID — most often
            # because the caller hung up and our hangup webhook never
            # arrived (e.g. tunnel down). The goal of "make sure this call
            # isn't live" is already satisfied, so this is a success, not
            # a failure to surface to the caller.
            pass

    def transfer_call(
        self, *, call_id: str, answer_url: str, callback_url: str | None = None,
    ) -> TransferCallResult:
        if not call_id:
            raise ValueError("A provider call ID is required")
        if not answer_url.lower().startswith(("https://", "http://")):
            raise ValueError("The transfer answer URL must be HTTP(S)")
        kwargs: dict[str, Any] = {}
        if callback_url:
            # Plivo's "Update Live Call" API is asynchronous: a 2xx response
            # here only means the redirect request was accepted, not that it
            # was actually executed. Without this callback there is no way
            # to know whether Plivo ever fetched answer_url at all.
            kwargs["callback_url"] = callback_url
            kwargs["callback_method"] = "POST"
        response = self.client.calls.update(
            call_uuid=call_id,
            legs="aleg",
            aleg_url=answer_url,
            aleg_method="POST",
            **kwargs,
        )
        return TransferCallResult(
            provider=self.name,
            call_id=call_id,
            metadata={
                "api_id": _value(response, "api_id"),
                "message": _value(response, "message"),
            },
        )

    def get_call(self, call_id: str) -> CallDetails:
        item = self.client.calls.get(call_uuid=call_id)
        return CallDetails(
            provider=self.name,
            call_id=call_id,
            status=_value(item, "call_state") or _value(item, "call_status"),
            duration_seconds=int(_value(item, "call_duration", 0) or 0),
            billed_duration_seconds=int(
                _value(item, "billed_duration", _value(item, "bill_duration", 0)) or 0
            ),
            cost_usd=abs(float(_value(item, "total_amount", 0) or 0)),
            metadata={"hangup_cause": _value(item, "hangup_cause_name")},
        )

    def get_recording(self, recording_id: str) -> tuple[bytes, str]:
        import requests

        recording = self.client.recordings.get(recording_id=recording_id)
        url = str(_value(recording, "recording_url") or "")
        if not url:
            raise RuntimeError("Plivo recording URL is unavailable")
        response = requests.get(
            url, auth=(self.auth_id, self.auth_token), timeout=30,
            allow_redirects=True,
        )
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "audio/mpeg").split(";", 1)[0]
        return response.content, content_type

    def validate_callback(
        self, *, method: str, url: str, nonce: str,
        signature: str, params: Mapping[str, Any],
    ) -> bool:
        if not nonce or not signature or not self.auth_token:
            return False
        try:
            from plivo.utils import validate_v3_signature
        except ImportError:
            return False
        if method.upper() == "GET":
            return bool(validate_v3_signature(
                "GET", url, nonce, self.auth_token, signature
            ))
        return bool(validate_v3_signature(
            method.upper(), url, nonce, self.auth_token, signature, dict(params)
        ))
