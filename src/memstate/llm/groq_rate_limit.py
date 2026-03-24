"""Groq API rate-limit detection and backoff helpers."""

from __future__ import annotations

import re

import httpx

_RATE_LIMIT_TRY_AGAIN_RE = re.compile(r"try again in ([\d.]+)\s*s", re.IGNORECASE)


def groq_response_is_rate_limited(response: httpx.Response) -> bool:
    if response.status_code == 429:
        return True
    if response.status_code != 400:
        return False
    try:
        j = response.json()
    except Exception:
        return False
    err = j.get("error")
    if not isinstance(err, dict):
        return False
    code = err.get("code")
    if code == "rate_limit_exceeded":
        return True
    msg = str(err.get("message") or "").lower()
    return "rate limit" in msg or "tokens per minute" in msg


def groq_rate_limit_sleep_seconds(response: httpx.Response, *, default_seconds: float = 3.0) -> float:
    """Seconds to wait before retrying (from Retry-After or error message)."""
    if response.status_code == 429:
        ra = response.headers.get("Retry-After")
        if ra:
            try:
                return float(ra)
            except ValueError:
                pass
    try:
        j = response.json()
    except Exception:
        return default_seconds
    err = j.get("error")
    if isinstance(err, dict):
        msg = str(err.get("message") or "")
        m = _RATE_LIMIT_TRY_AGAIN_RE.search(msg)
        if m:
            return float(m.group(1)) + 0.35
    return default_seconds
