"""Ollama /api/chat loop with tool calling."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from memstate.llm.agent_viz import build_viz_hint
from memstate.llm.tools_schema import DEFAULT_LLM_SYSTEM_PROMPT_FALLBACK, OLLAMA_TOOLS
from memstate.llm.tool_runner import MemoryToolRunner

DEFAULT_MAX_TOOL_ROUNDS = 32

ChatEventCallback = Callable[[dict[str, Any]], Awaitable[None] | None]


async def _emit(on_event: ChatEventCallback | None, event: dict[str, Any]) -> None:
    if on_event is None:
        return
    out = on_event(event)
    if out is not None:
        await out


def _parse_tool_args(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            v = json.loads(raw)
            return v if isinstance(v, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


async def run_ollama_chat(
    *,
    base_url: str,
    model: str,
    messages: list[dict[str, Any]],
    runner: MemoryToolRunner,
    system_prompt: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    max_tool_rounds: int = DEFAULT_MAX_TOOL_ROUNDS,
    on_event: ChatEventCallback | None = None,
) -> tuple[str, list[dict[str, Any]], str]:
    """
    Send messages to Ollama with tools; execute tool calls until the model replies with text.
    Returns (assistant_text, tool_log, model_used).
    If system_prompt is None, uses DEFAULT_LLM_SYSTEM_PROMPT_FALLBACK (base system text plus topic-vs-entity).
    """
    url = f"{base_url.rstrip('/')}/api/chat"
    sys = system_prompt if system_prompt is not None else DEFAULT_LLM_SYSTEM_PROMPT_FALLBACK
    tool_defs = tools if tools is not None else OLLAMA_TOOLS
    full: list[dict[str, Any]] = [{"role": "system", "content": sys}, *messages]
    tool_log: list[dict[str, Any]] = []
    used_model = model
    tool_index = 0

    rounds = max(1, int(max_tool_rounds))
    async with httpx.AsyncClient(timeout=180.0) as client:
        for _ in range(rounds):
            await _emit(on_event, {"type": "llm_round"})

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
                args = _parse_tool_args(raw_args)
                viz_start = build_viz_hint(name, args, None)
                await _emit(
                    on_event,
                    {
                        "type": "tool_start",
                        "index": tool_index,
                        "tool": name,
                        "args": args,
                        "viz": viz_start,
                    },
                )
                result = runner.execute(name, raw_args)
                viz_end = build_viz_hint(name, args, result)
                entry = {"tool": name, "args": args, "result": result}
                tool_log.append(entry)
                await _emit(
                    on_event,
                    {
                        "type": "tool_end",
                        "index": tool_index,
                        "tool": name,
                        "args": args,
                        "result": result,
                        "viz": viz_end,
                    },
                )
                tool_index += 1
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
