"""Groq OpenAI-compatible chat completions with tool calling."""

from __future__ import annotations

import asyncio
import json
import random
from typing import Any

import httpx

from memstate.config import get_settings
from memstate.llm.groq_rate_limit import (
    groq_rate_limit_sleep_seconds,
    groq_response_is_rate_limited,
)
from memstate.llm.tools_schema import DEFAULT_LLM_SYSTEM_PROMPT_FALLBACK, OLLAMA_TOOLS
from memstate.llm.tool_runner import MemoryToolRunner

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MAX_TOOL_ROUNDS = 32

# Long read timeout: large prompts + tool rounds can exceed Cloudflare/Groq limits anyway,
# but a generous client timeout avoids local premature aborts on slow responses.
GROQ_HTTP_TIMEOUT = httpx.Timeout(connect=30.0, read=600.0, write=120.0, pool=30.0)

# Re-use same JSON-schema tools as Ollama (OpenAI format).
MEMORY_TOOLS = OLLAMA_TOOLS


async def groq_post_chat_completions_with_retries(
    client: httpx.AsyncClient,
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """
    POST chat/completions; retry on rate limit (429 / rate_limit_exceeded).
    Used by intent classification and other single-shot Groq calls.
    """
    settings = get_settings()
    cap = max(1, int(settings.groq_rate_limit_max_retries))
    backoff_cap = float(settings.groq_rate_limit_backoff_cap_seconds)
    last: httpx.Response | None = None
    for attempt in range(cap):
        r = await client.post(GROQ_CHAT_URL, headers=headers, json=payload)
        last = r
        if r.status_code == 200:
            return r.json()
        if groq_response_is_rate_limited(r) and attempt < cap - 1:
            sleep_s = min(groq_rate_limit_sleep_seconds(r), backoff_cap)
            sleep_s += random.uniform(0.05, 0.45)
            await asyncio.sleep(sleep_s)
            continue
        r.raise_for_status()
    if last is not None:
        last.raise_for_status()
    raise RuntimeError("Groq request failed")


async def _groq_completion_post(
    client: httpx.AsyncClient,
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """
    POST chat/completions; retry on Groq output_parse_failed (some models emit plain text
    instead of valid tool calls) and on rate limits.

    Retries use tool_choice=required so the model must emit at least one tool call, without
    locking to a single tool name (locking caused tool_use_failed when the model correctly
    chose memory_list_topics before memory_reorganize_*).
    """
    settings = get_settings()
    max_rate = max(1, int(settings.groq_rate_limit_max_retries))
    backoff_cap = float(settings.groq_rate_limit_backoff_cap_seconds)
    parse_fixes = 0

    while True:
        r: httpx.Response | None = None
        for _ in range(max_rate):
            r = await client.post(GROQ_CHAT_URL, headers=headers, json=payload)
            if r.status_code == 200:
                return r.json()
            if groq_response_is_rate_limited(r):
                sleep_s = min(groq_rate_limit_sleep_seconds(r), backoff_cap) + random.uniform(0.05, 0.55)
                await asyncio.sleep(sleep_s)
                continue
            break

        if r is None:
            raise RuntimeError("Groq request failed")

        if r.status_code == 400:
            try:
                err_body = r.json()
            except Exception:
                r.raise_for_status()
                raise
            code = (err_body.get("error") or {}).get("code")
            if code == "output_parse_failed" and parse_fixes < 2:
                payload["temperature"] = 0
                payload["tool_choice"] = "required"
                parse_fixes += 1
                continue
        r.raise_for_status()


async def run_groq_chat(
    *,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    runner: MemoryToolRunner,
    system_prompt: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    max_tool_rounds: int = DEFAULT_MAX_TOOL_ROUNDS,
) -> tuple[str, list[dict[str, Any]], str]:
    """
    Groq chat/completions with tools; execute tool calls until the model returns text.
    If system_prompt is None, uses DEFAULT_LLM_SYSTEM_PROMPT_FALLBACK (base system text plus topic-vs-entity).
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    sys = system_prompt if system_prompt is not None else DEFAULT_LLM_SYSTEM_PROMPT_FALLBACK
    tool_defs = tools if tools is not None else MEMORY_TOOLS
    full: list[dict[str, Any]] = [{"role": "system", "content": sys}, *messages]
    tool_log: list[dict[str, Any]] = []
    used_model = model

    rounds = max(1, int(max_tool_rounds))
    async with httpx.AsyncClient(timeout=GROQ_HTTP_TIMEOUT) as client:
        for _ in range(rounds):
            payload: dict[str, Any] = {
                "model": model,
                "messages": full,
                "tools": tool_defs,
                "tool_choice": "auto",
                "temperature": 0.2,
                "parallel_tool_calls": False,
            }

            data = await _groq_completion_post(
                client,
                headers=headers,
                payload=payload,
            )
            used_model = data.get("model") or model
            choice = (data.get("choices") or [{}])[0]
            msg = choice.get("message") or {}
            tool_calls = msg.get("tool_calls") or []

            if not tool_calls:
                text = (msg.get("content") or "").strip()
                if not tool_log:
                    return (text or "How can I help?", tool_log, used_model)
                return text, tool_log, used_model

            full.append(msg)

            for tc in tool_calls:
                tc_id = tc.get("id") or ""
                fn = tc.get("function") or {}
                name = fn.get("name") or ""
                raw_args = fn.get("arguments")
                result = runner.execute(name, raw_args)
                tool_log.append({"tool": name, "result": result})
                full.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )

        return (
            f"Stopped after {rounds} tool rounds (max {rounds}); check tool_log for partial results.",
            tool_log,
            used_model,
        )
