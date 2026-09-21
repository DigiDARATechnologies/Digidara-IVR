"""Canonical persisted lead-score policy.

Production lead scores come from the post-call conversation analysis and are
stored on call_logs. Structured lead rows copy that accepted value; they never
run a second scoring policy. The checkbox calculator is preview-only.
"""

from __future__ import annotations

from typing import Any, Optional


def normalize_score(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return None


def qualification_for_score(score: Optional[int]) -> Optional[str]:
    if score is None:
        return None
    if score >= 80:
        return "hot"
    if score >= 50:
        return "warm"
    if score >= 20:
        return "cold"
    return "unqualified"
