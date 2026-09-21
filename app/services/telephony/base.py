from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class CreateCallResult:
    provider: str
    request_id: str
    call_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CallDetails:
    provider: str
    call_id: str
    status: str | None = None
    duration_seconds: int = 0
    billed_duration_seconds: int = 0
    cost_usd: float = 0.0
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TransferCallResult:
    provider: str
    call_id: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


class TelephonyProvider(Protocol):
    name: str

    def is_configured(self) -> bool: ...

    def create_call(
        self, *, to: str, answer_url: str, ring_url: str,
        hangup_url: str, fallback_url: str, time_limit_seconds: int,
    ) -> CreateCallResult: ...

    def terminate_call(self, *, call_id: str | None, request_id: str | None) -> None: ...

    def transfer_call(
        self, *, call_id: str, answer_url: str, callback_url: str | None = None,
    ) -> TransferCallResult: ...

    def get_call(self, call_id: str) -> CallDetails: ...

    def get_recording(self, recording_id: str) -> tuple[bytes, str]: ...

    def validate_callback(
        self, *, method: str, url: str, nonce: str,
        signature: str, params: Mapping[str, Any],
    ) -> bool: ...
