"""Ollama /api/chat loop with tool calling."""

from __future__ import annotations

import json
from typing import Any

import httpx

from memstate.llm.tools_schema import OLLAMA_TOOLS, SYSTEM_PROMPT
from memstate.llm.tool_runner import MemoryToolRunner

MAX_TOOL_ROUNDS = 10


async def run_ollama_chat(
    *,
    base_url: str,
    model: str,
    messages: list[dict[str, Any]],
    runner: MemoryToolRunner,
) -> tuple[str, list[dict[str, Any]], str]:
    """
    Send messages to Ollama with tools; execute tool calls until the model replies with text.
    Returns (assistant_text, tool_log, model_used).
    """
    url = f"{base_url.rstrip('/')}/api/chat"
    full: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}, *messages]
    tool_log: list[dict[str, Any]] = []
    used_model = model

    async with httpx.AsyncClient(timeout=180.0) as client:
        for _ in range(MAX_TOOL_ROUNDS):
            has_tool_results = any(m.get("role") == "tool" for m in full)
            body: dict[str, Any] = {
                "model": model,
                "messages": full,
                "tools": OLLAMA_TOOLS,
                "stream": False,
            }
            # Prefer requiring tools until memory has been read/written this turn (Ollama 0.5+).
            if not has_tool_results:
                body["tool_choice"] = "required"

            r = await client.post(url, json=body)
            r.raise_for_status()
            data = r.json()
            used_model = data.get("model") or model
            msg = data.get("message") or {}
            tool_calls = msg.get("tool_calls") or []

            if not tool_calls:
                text = (msg.get("content") or "").strip()
                if not tool_log:
                    return (
                        "Cannot answer from memory: no tools were used. "
                        "Ensure your Ollama version supports tool_choice, or try another model.",
                        tool_log,
                        used_model,
                    )
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
            "Stopped after maximum tool rounds; check tool_log for partial results.",
            tool_log,
            used_model,
        )
