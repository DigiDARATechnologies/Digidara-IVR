"""Prompt token estimates for observability and UI guidance.

Realtime model tokenisation is provider-defined and Tamil text does not follow
the common English ``characters / 4`` rule. These values are estimates only;
actual Realtime usage events remain the billing source of truth.
"""

from __future__ import annotations

import math
import re
from typing import Dict


_TAMIL_RE = re.compile(r"[\u0B80-\u0BFF]")


def estimate_prompt_tokens(text: str) -> int:
    """Return a conservative token estimate without adding a runtime dependency."""
    value = text or ""
    if not value:
        return 0
    tamil_chars = len(_TAMIL_RE.findall(value))
    other_chars = max(0, len(value) - tamil_chars)
    # Tamil Unicode commonly tokenises more densely than English. Keep this
    # intentionally conservative so budget warnings are useful.
    return int(math.ceil(tamil_chars / 1.8 + other_chars / 4.0))


def prompt_token_breakdown(
    *,
    static_policy: str = "",
    campaign_context: str = "",
    customer_context: str = "",
    knowledge_context: str = "",
    other: str = "",
) -> Dict[str, int | str]:
    values = {
        "static_policy_tokens": estimate_prompt_tokens(static_policy),
        "campaign_tokens": estimate_prompt_tokens(campaign_context),
        "customer_context_tokens": estimate_prompt_tokens(customer_context),
        "knowledge_tokens": estimate_prompt_tokens(knowledge_context),
        "other_tokens": estimate_prompt_tokens(other),
    }
    return {
        "method": "conservative_character_estimate",
        **values,
        "total_estimated_tokens": sum(values.values()),
    }
