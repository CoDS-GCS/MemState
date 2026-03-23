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
from memstate.llm.text_chunking import build_internal_chunk_user_message, chunk_text_with_overlap
from memstate.llm.tool_runner import MemoryToolRunner
from memstate.llm.tools_schema import IntentRoute, build_chat_system_prompt, tools_for_intent_route
from memstate.store.graph_store import GraphStore

router = APIRouter(prefix="/api/llm", tags=["llm"])

_INTENT_TURNS_CAP = 64
_MAX_TOOL_ROUNDS_CAP = 256


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


def _groq_upstream_error_message(response: httpx.Response | None) -> str:
    """Short, user-safe message; never return HTML error pages to the client."""
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
    max_tool_rounds: int | None = Field(
        None,
        ge=1,
        le=_MAX_TOOL_ROUNDS_CAP,
        description="Max LLM↔API rounds while tools are requested (overrides MEMSTATE_CHAT_MAX_TOOL_ROUNDS).",
    )
    internal_chunk: bool = Field(
        False,
        description=(
            "If True and the last user message exceeds the chunk threshold, split it server-side into "
            "overlapping segments (one LLM run per segment; graph persists). Avoids multi-request client loops."
        ),
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


def _resolve_max_tool_rounds(body: ChatBody, settings: Settings) -> int:
    n = body.max_tool_rounds if body.max_tool_rounds is not None else settings.chat_max_tool_rounds
    return max(1, min(int(n), _MAX_TOOL_ROUNDS_CAP))


def _resolve_base_url(body: ChatBody, settings: Settings) -> str:
    if body.ollama_base_url and body.ollama_base_url.strip():
        return validate_client_ollama_url(body.ollama_base_url, settings)
    try:
        return normalize_ollama_base_url(settings.ollama_base_url)
    except ValueError:
        return settings.ollama_base_url.rstrip("/")


IntentSource = Literal["classifier", "override"]


async def _resolve_intent_route(
    body: ChatBody,
    *,
    dialogue: list[dict[str, Any]],
    settings: Settings,
    ollama_base: str,
    groq_key: str,
    model: str,
) -> tuple[IntentRoute, IntentSource]:
    if body.intent_override is not None:
        return body.intent_override, "override"
    text = dialogue_text_for_classifier(dialogue)
    route = await classify_intent(
        provider=body.provider,
        model=model,
        ollama_base_url=ollama_base,
        groq_api_key=groq_key,
        dialogue_text=text,
    )
    return route, "classifier"


_INTENT_CLIP_CHARS = 12_000


def _intent_dialogue_for_long_last_message(
    dialogue: list[dict[str, Any]], *, max_chars: int = _INTENT_CLIP_CHARS
) -> list[dict[str, Any]]:
    """Clip the last user message for intent classification when it is huge."""
    if not dialogue or dialogue[-1].get("role") != "user":
        return dialogue
    last = str(dialogue[-1].get("content") or "")
    if len(last) <= max_chars:
        return dialogue
    clipped = last[:max_chars] + "\n[... truncated for intent routing ...]"
    return dialogue[:-1] + [{"role": "user", "content": clipped}]


async def _chat_internal_chunked(
    body: ChatBody,
    dialogue: list[dict[str, Any]],
    store: GraphStore,
    settings: Settings,
    model: str,
    groq_key: str,
    ollama_base: str,
    base_tool_rounds: int,
) -> dict[str, Any]:
    """One LLM run per segment; graph store persists. Prior dialogue turns are preserved; only the last user message was split."""
    prior = dialogue[:-1]
    last_full = str(dialogue[-1].get("content") or "")
    chunks = chunk_text_with_overlap(
        last_full,
        settings.chat_chunk_max_chars,
        settings.chat_chunk_overlap,
    )
    dialogue_for_route = _intent_dialogue_for_long_last_message(dialogue)
    route, intent_source = await _resolve_intent_route(
        body,
        dialogue=dialogue_for_route,
        settings=settings,
        ollama_base=ollama_base,
        groq_key=groq_key,
        model=model,
    )
    seg_rounds = max(base_tool_rounds, settings.chat_chunk_per_segment_tool_rounds)
    tool_defs = tools_for_intent_route(route)
    sys_prompt = build_chat_system_prompt(route)

    replies: list[str] = []
    merged_log: list[dict[str, Any]] = []
    used_model = model

    for i, chunk in enumerate(chunks):
        user_msg = build_internal_chunk_user_message(
            chunk,
            i + 1,
            len(chunks),
            settings.chat_chunk_overlap,
        )
        messages = prior + [{"role": "user", "content": user_msg}]
        runner = MemoryToolRunner(
            store,
            chat_route=route,
            query_field_salience_bump=settings.query_field_salience_bump,
            field_salience_max=settings.field_salience_max,
        )
        if body.provider == "groq":
            reply, tool_log, used = await run_groq_chat(
                api_key=groq_key,
                model=model,
                messages=messages,
                runner=runner,
                system_prompt=sys_prompt,
                tools=tool_defs,
                max_tool_rounds=seg_rounds,
            )
        else:
            reply, tool_log, used = await run_ollama_chat(
                base_url=ollama_base,
                model=model,
                messages=messages,
                runner=runner,
                system_prompt=sys_prompt,
                tools=tool_defs,
                max_tool_rounds=seg_rounds,
            )
        used_model = used
        replies.append(reply)
        for entry in tool_log:
            merged_log.append({"segment": i + 1, **entry})

    if len(chunks) == 1:
        combined = replies[0]
    else:
        combined = (
            f"(Long message processed in {len(chunks)} internal segments.)\n\n"
            + "\n\n---\n\n".join(
                f"[Segment {si + 1}/{len(chunks)}]\n{r}" for si, r in enumerate(replies)
            )
        )

    return {
        "reply": combined,
        "tool_log": merged_log,
        "model": used_model,
        "provider": body.provider,
        "intent": route,
        "intent_source": intent_source,
        "max_tool_rounds": seg_rounds,
        "internal_chunked": True,
        "segments": len(chunks),
    }


@router.post("/chat")
async def llm_chat(body: ChatBody, store: GraphStore = Depends(get_graph_store)) -> dict[str, Any]:
    settings = get_settings()
    dialogue = _prepare_chat_messages(body, settings)
    model = (
        (body.model or (settings.groq_model if body.provider == "groq" else settings.ollama_model))
        .strip()
        or (settings.groq_model if body.provider == "groq" else settings.ollama_model)
    )
    groq_key = (settings.groq_api_key or "").strip()
    ollama_base = _resolve_base_url(body, settings)
    tool_rounds = _resolve_max_tool_rounds(body, settings)

    last_full = str(dialogue[-1].get("content") or "")
    if body.internal_chunk and len(last_full) > settings.chat_chunk_threshold_chars:
        if body.provider == "groq" and not groq_key:
            raise HTTPException(
                status_code=503,
                detail="Groq is not configured. Set GROQ_API_KEY in .env (see .env.example).",
            )
        try:
            return await _chat_internal_chunked(
                body,
                dialogue,
                store,
                settings,
                model,
                groq_key,
                ollama_base,
                tool_rounds,
            )
        except httpx.HTTPStatusError as e:
            if body.provider == "groq":
                detail = _groq_upstream_error_message(e.response)
            else:
                detail = e.response.text if e.response is not None else str(e)
                detail = f"Ollama error: {detail}"
            raise HTTPException(status_code=502, detail=detail) from e
        except httpx.RequestError as e:
            if body.provider == "groq":
                raise HTTPException(
                    status_code=503,
                    detail=f"Cannot reach Groq API. Check network and API key. ({e})",
                ) from e
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

    if body.provider == "groq":
        if not groq_key:
            raise HTTPException(
                status_code=503,
                detail="Groq is not configured. Set GROQ_API_KEY in .env (see .env.example).",
            )
        try:
            route, intent_source = await _resolve_intent_route(
                body, dialogue=dialogue, settings=settings, ollama_base=ollama_base, groq_key=groq_key, model=model
            )
            runner = MemoryToolRunner(
                store,
                chat_route=route,
                query_field_salience_bump=settings.query_field_salience_bump,
                field_salience_max=settings.field_salience_max,
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
                max_tool_rounds=tool_rounds,
            )
        except httpx.HTTPStatusError as e:
            detail = _groq_upstream_error_message(e.response)
            raise HTTPException(status_code=502, detail=detail) from e
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
            "intent_source": intent_source,
            "max_tool_rounds": tool_rounds,
        }

    # Ollama
    try:
        route, intent_source = await _resolve_intent_route(
            body, dialogue=dialogue, settings=settings, ollama_base=ollama_base, groq_key=groq_key, model=model
        )
        runner = MemoryToolRunner(
            store,
            chat_route=route,
            query_field_salience_bump=settings.query_field_salience_bump,
            field_salience_max=settings.field_salience_max,
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
            max_tool_rounds=tool_rounds,
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
        "intent_source": intent_source,
        "max_tool_rounds": tool_rounds,
    }
