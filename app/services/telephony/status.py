"""Pure provider-to-product lifecycle normalization."""


def map_plivo_status(value: str | None, hangup_cause: str | None = None) -> str:
    status = (value or "").strip().lower().replace("_", "-")
    cause = (hangup_cause or "").strip().lower()
    normalized_cause = cause.replace("_", " ").replace("-", " ")
    if "busy" in normalized_cause:
        return "busy"
    if "no answer" in normalized_cause or "timeout" in normalized_cause:
        return "no-answer"
    if "cancel" in normalized_cause:
        return "canceled"
    if any(word in normalized_cause for word in (
        "reject", "declin", "forbidden", "invalid", "error", "failed", "unreachable",
    )):
        return "failed"
    if "normal hangup" in normalized_cause or "end of xml instructions" in normalized_cause:
        return "completed"
    if status in {"queued", "initiated"}:
        return "initiated"
    if status in {"ring", "ringing"}:
        return "ringing"
    if status in {"answer", "answered", "in-progress", "in progress", "ongoing"}:
        return "in-progress"
    if status in {"cancel", "cancelled", "canceled"}:
        return "canceled"
    if status in {"no-answer", "no answer", "timeout"}:
        return "no-answer"
    if status == "busy":
        return "busy"
    if status in {"failed", "rejected"}:
        return "failed"
    if status in {"completed", "hangup"}:
        return "completed"
    return status or "initiated"
