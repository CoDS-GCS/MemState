"""HTTP API for LLM chat (Ollama + Groq + memory tools)."""

from __future__ import annotations

from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from memstate.api.deps import get_graph_store
from memstate.config import Settings, get_settings
from memstate.llm.groq_chat import run_groq_chat
from memstate.llm.intent_router import classify_intent, dialogue_text_for_classifier
from memstate.llm.ollama_chat import run_ollama_chat
from memstate.llm.ollama_url import normalize_ollama_base_url, validate_client_ollama_url
from memstate.llm.tool_runner import MemoryToolRunner
from memstate.llm.tools_schema import IntentRoute, build_chat_system_prompt, tools_for_intent_route
from memstate.store.graph_store import GraphStore

router = APIRouter(prefix="/api/llm", tags=["llm"])

_INTENT_TURNS_CAP = 64


def _normalize_dialogue_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep user/assistant turns with non-empty string content."""
    out: list[dict[str, Any]] = []
    for m in messages:
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        c = m.get("content")
        if c is None or not str(c).strip():
            continue
        out.append({"role": role, "content": str(c).strip()})
    return out


def _clip_dialogue_to_last_k_turns(messages: list[dict[str, Any]], k: int) -> list[dict[str, Any]]:
    """
    Keep the last *k* dialogue turns. One turn starts at a user message and includes
    following assistant message(s) until the next user.
    """
    if k <= 0 or not messages:
        return messages
    turns: list[list[dict[str, Any]]] = []
    buf: list[dict[str, Any]] = []
    for m in messages:
        if m.get("role") == "user" and buf:
            turns.append(buf)
            buf = [m]
        else:
            buf.append(m)
    if buf:
        turns.append(buf)
    selected = turns[-k:] if len(turns) > k else turns
    return [msg for turn in selected for msg in turn]


class ChatBody(BaseModel):
    messages: list[dict[str, Any]] = Field(
        ...,
        description="Chat thread: user and optional assistant messages; last message must be user.",
    )
    provider: Literal["ollama", "groq"] = "ollama"
    model: str | None = Field(None, description="Model id (provider-specific)")
    ollama_base_url: str | None = Field(
        None,
        description="Override Ollama API base (Ollama provider only).",
    )
    intent_turns: int | None = Field(
        None,
        ge=1,
        le=_INTENT_TURNS_CAP,
        description="How many dialogue turns to include (overrides MEMSTATE_CHAT_INTENT_TURNS).",
    )
    intent_override: IntentRoute | None = Field(
        None,
        description="Skip LLM intent classification and fix route (query|ingest|both).",
    )


def _prepare_chat_messages(body: ChatBody, settings: Settings) -> list[dict[str, Any]]:
    norm = _normalize_dialogue_messages(body.messages)
    if not norm:
        raise HTTPException(status_code=400, detail="At least one non-empty user message is required.")
    if norm[-1].get("role") != "user":
        raise HTTPException(
            status_code=400,
            detail="Last message must be from the user.",
        )
    k = body.intent_turns if body.intent_turns is not None else settings.chat_intent_turns
    k = max(1, min(int(k), _INTENT_TURNS_CAP))
    return _clip_dialogue_to_last_k_turns(norm, k)


def _resolve_base_url(body: ChatBody, settings: Settings) -> str:
    if body.ollama_base_url and body.ollama_base_url.strip():
        return validate_client_ollama_url(body.ollama_base_url, settings)
    try:
        return normalize_ollama_base_url(settings.ollama_base_url)
    except ValueError:
        return settings.ollama_base_url.rstrip("/")


async def _resolve_intent_route(
    body: ChatBody,
    *,
    dialogue: list[dict[str, Any]],
    settings: Settings,
    ollama_base: str,
    groq_key: str,
    model: str,
) -> IntentRoute:
    if body.intent_override is not None:
        return body.intent_override
    text = dialogue_text_for_classifier(dialogue)
    return await classify_intent(
        provider=body.provider,
        model=model,
        ollama_base_url=ollama_base,
        groq_api_key=groq_key,
        dialogue_text=text,
    )


@router.post("/chat")
async def llm_chat(body: ChatBody, store: GraphStore = Depends(get_graph_store)) -> dict[str, Any]:
    settings = get_settings()
    runner = MemoryToolRunner(store)
    dialogue = _prepare_chat_messages(body, settings)
    model = (
        (body.model or (settings.groq_model if body.provider == "groq" else settings.ollama_model))
        .strip()
        or (settings.groq_model if body.provider == "groq" else settings.ollama_model)
    )
    groq_key = (settings.groq_api_key or "").strip()
    ollama_base = _resolve_base_url(body, settings)

    if body.provider == "groq":
        if not groq_key:
            raise HTTPException(
                status_code=503,
                detail="Groq is not configured. Set GROQ_API_KEY in .env (see .env.example).",
            )
        try:
            route = await _resolve_intent_route(
                body, dialogue=dialogue, settings=settings, ollama_base=ollama_base, groq_key=groq_key, model=model
            )
            tool_defs = tools_for_intent_route(route)
            sys_prompt = build_chat_system_prompt(route)
            reply, tool_log, used = await run_groq_chat(
                api_key=groq_key,
                model=model,
                messages=dialogue,
                runner=runner,
                system_prompt=sys_prompt,
                tools=tool_defs,
            )
        except httpx.HTTPStatusError as e:
            detail = e.response.text if e.response is not None else str(e)
            raise HTTPException(status_code=502, detail=f"Groq error: {detail}") from e
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=503,
                detail=f"Cannot reach Groq API. Check network and API key. ({e})",
            ) from e
        return {
            "reply": reply,
            "tool_log": tool_log,
            "model": used,
            "provider": "groq",
            "intent": route,
        }

    # Ollama
    try:
        route = await _resolve_intent_route(
            body, dialogue=dialogue, settings=settings, ollama_base=ollama_base, groq_key=groq_key, model=model
        )
        tool_defs = tools_for_intent_route(route)
        sys_prompt = build_chat_system_prompt(route)
        reply, tool_log, used = await run_ollama_chat(
            base_url=ollama_base,
            model=model,
            messages=dialogue,
            runner=runner,
            system_prompt=sys_prompt,
            tools=tool_defs,
        )
    except httpx.HTTPStatusError as e:
        detail = e.response.text if e.response is not None else str(e)
        raise HTTPException(status_code=502, detail=f"Ollama error: {detail}") from e
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Cannot reach Ollama at {ollama_base}. "
                "Start the Ollama app (or run `ollama serve`), pull a model (`ollama pull llama3.2`), "
                "then set the Ollama URL in the sidebar or MEMSTATE_OLLAMA_BASE_URL. "
                f"Details: {e}"
            ),
        ) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return {
        "reply": reply,
        "tool_log": tool_log,
        "model": used,
        "provider": "ollama",
        "intent": route,
    }
