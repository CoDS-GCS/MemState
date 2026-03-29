"""Groq Whisper speech-to-text (OpenAI-compatible transcription API)."""

from __future__ import annotations

import httpx
from fastapi import HTTPException

from memstate.config import Settings

_GROQ_TRANSCRIBE_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
_MAX_TRANSCRIBE_BYTES = 25 * 1024 * 1024


def _groq_transcribe_error_message(response: httpx.Response | None) -> str:
    if response is None:
        return "No response from Groq."
    text = response.text or ""
    status = response.status_code
    ct = (response.headers.get("content-type") or "").lower()
    if status != 524 and "application/json" in ct and text.strip().startswith("{"):
        try:
            j = response.json()
            err = j.get("error")
            if isinstance(err, dict):
                msg = err.get("message") or str(err)
                code = err.get("code")
                if code:
                    return f"Groq: {msg} (code {code})"
                return f"Groq: {msg}"
        except Exception:
            pass
    if status == 524 or "Error code 524" in text or "A timeout occurred" in text:
        return (
            "Groq timed out (HTTP 524). Very large or slow requests often fail at the edge. "
            "Split your text into smaller messages, or use the Ollama provider locally."
        )
    st = text.strip()
    if st.startswith("<!DOCTYPE") or st.startswith("<html"):
        return (
            f"Groq returned an HTML error page (HTTP {status}). This is usually a timeout or overload—"
            "try shorter input, retry later, or use Ollama."
        )
    if len(text) > 1200:
        return f"Groq error (HTTP {status}): {text[:1200]}…"
    return text or f"HTTP {status}"


async def transcribe_audio_bytes(
    raw: bytes,
    *,
    filename: str,
    content_type: str,
    settings: Settings,
) -> str:
    """
    Send raw audio to Groq Whisper; return plain transcript text.
    Raises HTTPException for config, size, and upstream errors.
    """
    key = (settings.groq_api_key or "").strip()
    if not key:
        raise HTTPException(
            status_code=503,
            detail="Speech-to-text needs GROQ_API_KEY on the server (.env). Uses Groq Whisper.",
        )
    if len(raw) > _MAX_TRANSCRIBE_BYTES:
        raise HTTPException(status_code=413, detail="Audio too large (max 25 MB).")
    if len(raw) < 200:
        raise HTTPException(status_code=400, detail="Audio too short or empty.")
    name = filename or "audio.webm"
    ctype = content_type or "application/octet-stream"
    files = {"file": (name, raw, ctype)}
    data = {"model": settings.groq_whisper_model}
    headers = {"Authorization": f"Bearer {key}"}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=30.0)) as client:
            r = await client.post(_GROQ_TRANSCRIBE_URL, headers=headers, files=files, data=data)
            r.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=_groq_transcribe_error_message(e.response),
        ) from e
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Could not reach Groq for transcription: {e}",
        ) from e
    try:
        out = r.json()
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Groq transcription returned non-JSON.",
        )
    text = out.get("text")
    if not isinstance(text, str):
        raise HTTPException(
            status_code=502,
            detail="Groq transcription response missing text.",
        )
    return text.strip()
