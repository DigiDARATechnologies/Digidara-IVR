"""Thread-safe sliding window in-memory rate limiter for production endpoints."""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from typing import Any, Optional
from fastapi import HTTPException, Request


class SlidingWindowRateLimiter:
    """Sliding-window counter rate limiter per client key (e.g., client IP).

    Thread-safe and requires no third-party services like Redis for single-instance
    production deployments. Automatically purges expired timestamps.
    """

    def __init__(self, default_limit: int = 10, window_seconds: int = 60) -> None:
        self.default_limit = default_limit
        self.window_seconds = window_seconds
        self._records: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def get_client_ip(self, request: Any) -> str:
        """Safely extract client IP respecting trusted proxy headers if configured."""
        if request is None:
            return "127.0.0.1"
        client = getattr(request, "client", None)
        client_host = getattr(client, "host", None) or "127.0.0.1"
        trusted_proxies = (os.getenv("TRUSTED_PROXY_IPS") or "").strip()
        if trusted_proxies:
            proxies = {p.strip() for p in trusted_proxies.split(",") if p.strip()}
            if client_host in proxies:
                headers = getattr(request, "headers", {}) or {}
                forwarded_for = headers.get("X-Forwarded-For")
                if forwarded_for:
                    # The first IP in X-Forwarded-For is the initial client IP
                    return forwarded_for.split(",")[0].strip()
        return client_host

    def check(
        self,
        key: str,
        limit: Optional[int] = None,
        window_seconds: Optional[int] = None,
    ) -> tuple[bool, int, int]:
        """Check if request is allowed for the key.

        Returns:
            (is_allowed, remaining_attempts, retry_after_seconds)
        """
        max_allowed = limit if limit is not None else self.default_limit
        window = window_seconds if window_seconds is not None else self.window_seconds
        now = time.monotonic()
        cutoff = now - window

        with self._lock:
            timestamps = self._records[key]
            # Evict timestamps outside the sliding window
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()

            if len(timestamps) >= max_allowed:
                # Oldest timestamp determines when the earliest slot frees up
                oldest = timestamps[0]
                retry_after = max(1, int(window - (now - oldest)))
                return False, 0, retry_after

            timestamps.append(now)
            remaining = max_allowed - len(timestamps)
            return True, remaining, 0

    def enforce(
        self,
        request: Request,
        action: str,
        limit: Optional[int] = None,
        window_seconds: Optional[int] = None,
    ) -> None:
        """Enforce rate limit for request or raise HTTP 429."""
        client_ip = self.get_client_ip(request)
        key = f"{action}:{client_ip}"
        allowed, remaining, retry_after = self.check(
            key, limit=limit, window_seconds=window_seconds
        )
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "rate_limit_exceeded",
                    "message": "Too many requests. Please try again later.",
                    "retry_after_seconds": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

    def reset(self) -> None:
        """Clear all rate limit records (primarily for testing)."""
        with self._lock:
            self._records.clear()


# Global rate limiter instance
limiter = SlidingWindowRateLimiter()


def get_auth_rate_limit() -> int:
    try:
        return int(os.getenv("AUTH_RATE_LIMIT_PER_MINUTE", "10"))
    except ValueError:
        return 10


def get_bootstrap_rate_limit() -> int:
    try:
        return int(os.getenv("BOOTSTRAP_RATE_LIMIT_PER_MINUTE", "5"))
    except ValueError:
        return 5
