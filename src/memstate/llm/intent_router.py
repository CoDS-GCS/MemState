"""Classify user intent (query / ingest / both) before the tool-calling chat phase."""

from __future__ import annotations

import re
from typing import Any, Literal

import httpx

from memstate.llm.groq_chat import GROQ_CHAT_URL, groq_post_chat_completions_with_retries
from memstate.llm.tools_schema import INTENT_CLASSIFY_SYSTEM, IntentRoute

Provider = Literal["ollama", "groq"]


def _parse_intent_token(raw: str) -> IntentRoute:
    if not raw or not str(raw).strip():
        return "both"
    m = re.search(r"\b(query|ingest|both)\b", str(raw).lower())
    if m:
        return m.group(1)  # type: ignore[return-value]
    return "both"


async def classify_intent(
    *,
    provider: Provider,
    model: str,
    ollama_base_url: str,
    groq_api_key: str,
    dialogue_text: str,
) -> IntentRoute:
    """
    Single LLM call, no tools: returns query | ingest | both.
    dialogue_text should include enough recent user/assistant context for pronouns.
    """
    user_block = (
        "Recent conversation (latest user message is last):\n\n"
        f"{dialogue_text.strip()}\n\n"
        "Classify the latest user message only."
    )
    if provider == "groq":
        return await _classify_groq(api_key=groq_api_key, model=model, user_content=user_block)
    return await _classify_ollama(base_url=ollama_base_url, model=model, user_content=user_block)


async def _classify_groq(*, api_key: str, model: str, user_content: str) -> IntentRoute:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": INTENT_CLASSIFY_SYSTEM},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0,
        "max_tokens": 16,
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        data = await groq_post_chat_completions_with_retries(
            client,
            headers=headers,
            payload=payload,
        )
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    text = (msg.get("content") or "").strip()
    return _parse_intent_token(text)


async def _classify_ollama(*, base_url: str, model: str, user_content: str) -> IntentRoute:
    url = f"{base_url.rstrip('/')}/api/chat"
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": INTENT_CLASSIFY_SYSTEM},
            {"role": "user", "content": user_content},
        ],
        "stream": False,
        "options": {"temperature": 0},
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(url, json=body)
        r.raise_for_status()
        data = r.json()
    msg = data.get("message") or {}
    text = (msg.get("content") or "").strip()
    return _parse_intent_token(text)


def dialogue_text_for_classifier(messages: list[dict[str, Any]], *, max_chars: int = 8000) -> str:
    """Compact transcript for intent classification."""
    lines: list[str] = []
    for m in messages:
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        c = str(m.get("content") or "").strip()
        if not c:
            continue
        if len(c) > 4000:
            c = c[:4000] + "…"
        lines.append(f"{role}: {c}")
    s = "\n\n".join(lines)
    if len(s) > max_chars:
        s = "…\n\n" + s[-max_chars:]
    return s
