"""Ollama /api/chat loop with tool calling."""

from __future__ import annotations

import json
from typing import Any

import httpx

from memstate.llm.tools_schema import OLLAMA_TOOLS, SYSTEM_PROMPT
from memstate.llm.tool_runner import MemoryToolRunner

DEFAULT_MAX_TOOL_ROUNDS = 32


async def run_ollama_chat(
    *,
    base_url: str,
    model: str,
    messages: list[dict[str, Any]],
    runner: MemoryToolRunner,
    system_prompt: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    max_tool_rounds: int = DEFAULT_MAX_TOOL_ROUNDS,
) -> tuple[str, list[dict[str, Any]], str]:
    """
    Send messages to Ollama with tools; execute tool calls until the model replies with text.
    Returns (assistant_text, tool_log, model_used).
    """
    url = f"{base_url.rstrip('/')}/api/chat"
    sys = system_prompt if system_prompt is not None else SYSTEM_PROMPT
    tool_defs = tools if tools is not None else OLLAMA_TOOLS
    full: list[dict[str, Any]] = [{"role": "system", "content": sys}, *messages]
    tool_log: list[dict[str, Any]] = []
    used_model = model

    rounds = max(1, int(max_tool_rounds))
    async with httpx.AsyncClient(timeout=180.0) as client:
        for _ in range(rounds):
            body: dict[str, Any] = {
                "model": model,
                "messages": full,
                "tools": tool_defs,
                "stream": False,
                "tool_choice": "auto",
            }

            r = await client.post(url, json=body)
            r.raise_for_status()
            data = r.json()
            used_model = data.get("model") or model
            msg = data.get("message") or {}
            tool_calls = msg.get("tool_calls") or []

            if not tool_calls:
                text = (msg.get("content") or "").strip()
                if not tool_log:
                    return (text or "How can I help?", tool_log, used_model)
                return text, tool_log, used_model

            full.append(msg)

            for tc in tool_calls:
                fn = tc.get("function") or {}
                name = fn.get("name") or ""
                raw_args = fn.get("arguments")
                result = runner.execute(name, raw_args)
                tool_log.append({"tool": name, "result": result})
                full.append(
                    {
                        "role": "tool",
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )

        return (
            f"Stopped after {rounds} tool rounds (max {rounds}); check tool_log for partial results.",
            tool_log,
            used_model,
        )
