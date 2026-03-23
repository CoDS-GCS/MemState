"""Groq OpenAI-compatible chat completions with tool calling."""

from __future__ import annotations

import json
from typing import Any

import httpx

from memstate.llm.tools_schema import OLLAMA_TOOLS, SYSTEM_PROMPT
from memstate.llm.tool_runner import MemoryToolRunner

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
MAX_TOOL_ROUNDS = 10

# Re-use same JSON-schema tools as Ollama (OpenAI format).
MEMORY_TOOLS = OLLAMA_TOOLS


async def run_groq_chat(
    *,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    runner: MemoryToolRunner,
) -> tuple[str, list[dict[str, Any]], str]:
    """
    Groq chat/completions with tools; execute tool calls until the model returns text.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    full: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}, *messages]
    tool_log: list[dict[str, Any]] = []
    used_model = model

    async with httpx.AsyncClient(timeout=180.0) as client:
        for _ in range(MAX_TOOL_ROUNDS):
            r = await client.post(
                GROQ_CHAT_URL,
                headers=headers,
                json={
                    "model": model,
                    "messages": full,
                    "tools": MEMORY_TOOLS,
                    "tool_choice": "auto",
                    "temperature": 0.2,
                },
            )
            r.raise_for_status()
            data = r.json()
            used_model = data.get("model") or model
            choice = (data.get("choices") or [{}])[0]
            msg = choice.get("message") or {}
            tool_calls = msg.get("tool_calls") or []

            if not tool_calls:
                text = (msg.get("content") or "").strip()
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
            "Stopped after maximum tool rounds; check tool_log for partial results.",
            tool_log,
            used_model,
        )
