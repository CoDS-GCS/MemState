"""HTTP API for LLM chat (Ollama + Groq + memory tools)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from memstate.api.deps import get_graph_store
from memstate.config import Settings, get_settings
from memstate.llm.groq_chat import run_groq_chat
from memstate.llm.groq_transcribe import transcribe_audio_bytes
from memstate.llm.intent_router import classify_intent, dialogue_text_for_classifier
from memstate.llm.ollama_chat import run_ollama_chat
from memstate.llm.ollama_url import normalize_ollama_base_url, validate_client_ollama_url
from memstate.llm.study_hierarchy import build_study_hierarchy, format_study_catalog_for_prompt, study_topic_kind
from memstate.llm.tool_runner import MemoryToolRunner
from memstate.llm.tools_schema import (
    IntentRoute,
    build_chat_system_prompt,
    build_study_phase_a_system_prompt,
    build_study_phase_b_system_prompt,
    tools_for_intent_route,
    tools_for_study_phase_a,
)
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
            "Legacy hint for long messages; the server now uses Study ingest when length and intent match "
            "(see study_ingest). Kept for older clients."
        ),
    )
    study_ingest: bool = Field(
        True,
        description=(
            "When True (default), long last user messages with ingest/both intent use the Study pipeline "
            "(hierarchy + two phases). Set False to force one LLM call (may hit context limits)."
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


def _build_system_context_prompt_block(store: GraphStore) -> str:
    row = store.get_system_config()
    if not row:
        return ""
    role = str(row.get("system_role") or "").strip()
    ctx = str(row.get("runtime_context") or "").strip()
    if not role and not ctx:
        return ""
    return (
        "Fixed system role/context (always apply this guidance):\n"
        f"- Role: {role or '(not set)'}\n"
        f"- Runtime context: {ctx or '(not set)'}"
    )


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


def _should_use_study(
    body: ChatBody,
    settings: Settings,
    last_user_len: int,
    route: IntentRoute,
) -> bool:
    if not body.study_ingest:
        return False
    if route not in ("ingest", "both"):
        return False
    return last_user_len > settings.chat_chunk_threshold_chars


ChatEventCallback = Callable[[dict[str, Any]], Awaitable[None] | None]


def _wrap_on_event(
    on_event: ChatEventCallback | None,
    *,
    phase: str | None = None,
) -> ChatEventCallback | None:
    if on_event is None:
        return None

    async def wrapped(event: dict[str, Any]) -> None:
        out = dict(event)
        if phase:
            out["phase"] = phase
        result = on_event(out)
        if result is not None:
            await result

    return wrapped


async def _chat_study_ingest(
    body: ChatBody,
    dialogue: list[dict[str, Any]],
    store: GraphStore,
    settings: Settings,
    model: str,
    groq_key: str,
    ollama_base: str,
    base_tool_rounds: int,
    route: IntentRoute,
    intent_source: IntentSource,
    on_event: ChatEventCallback | None = None,
) -> dict[str, Any]:
    """Study pipeline: phase A sandbox topics, phase B integrate with existing memory."""
    prior = dialogue[:-1]
    last_full = str(dialogue[-1].get("content") or "")
    hierarchy = build_study_hierarchy(last_full)
    sk = study_topic_kind(hierarchy.session_id)
    catalog = hierarchy.to_catalog_dict(max_units=500)
    catalog_block = format_study_catalog_for_prompt(hierarchy, max_units=200)

    phase_a_user = (
        "Study ingest — phase A (sandbox). Document follows the catalog. "
        f"All new topics must use topic_kind `{sk}` (enforced by tools).\n\n"
        f"{catalog_block}\n\n---DOCUMENT---\n\n{last_full}"
    )
    messages_a = prior + [{"role": "user", "content": phase_a_user}]
    seg_rounds = max(base_tool_rounds, settings.chat_chunk_per_segment_tool_rounds)
    tools_a = tools_for_study_phase_a()
    sys_a = build_study_phase_a_system_prompt(route)
    fixed_block = _build_system_context_prompt_block(store)
    if fixed_block:
        sys_a = f"{sys_a}\n\n{fixed_block}"
    runner_a = MemoryToolRunner(
        store,
        chat_route=route,
        query_field_salience_bump=settings.query_field_salience_bump,
        field_salience_max=settings.field_salience_max,
        study_session_kind=sk,
        study_catalog=catalog,
    )
    ev_a = _wrap_on_event(on_event, phase="study_a")
    if body.provider == "groq":
        reply_a, log_a, used_model = await run_groq_chat(
            api_key=groq_key,
            model=model,
            messages=messages_a,
            runner=runner_a,
            system_prompt=sys_a,
            tools=tools_a,
            max_tool_rounds=seg_rounds,
            on_event=ev_a,
        )
    else:
        reply_a, log_a, used_model = await run_ollama_chat(
            base_url=ollama_base,
            model=model,
            messages=messages_a,
            runner=runner_a,
            system_prompt=sys_a,
            tools=tools_a,
            max_tool_rounds=seg_rounds,
            on_event=ev_a,
        )

    delay = float(settings.study_phase_delay_seconds)
    if delay > 0:
        if on_event is not None:
            await on_event({"type": "study_phase_delay", "seconds": delay, "phase": "study_b"})
        await asyncio.sleep(delay)

    phase_b_user = (
        f"Study ingest — phase B (integrate). Session topic_kind: `{sk}`. "
        "Link these Study topics to the rest of memory; merge or consolidate when it improves organization. "
        "You may update topic_kind away from study:… when integrated."
    )
    messages_b = prior + [{"role": "user", "content": phase_b_user}]
    runner_b = MemoryToolRunner(
        store,
        chat_route=route,
        query_field_salience_bump=settings.query_field_salience_bump,
        field_salience_max=settings.field_salience_max,
    )
    tools_b = tools_for_intent_route(route)
    sys_b = build_study_phase_b_system_prompt(route)
    fixed_block = _build_system_context_prompt_block(store)
    if fixed_block:
        sys_b = f"{sys_b}\n\n{fixed_block}"
    ev_b = _wrap_on_event(on_event, phase="study_b")
    if body.provider == "groq":
        reply_b, log_b, used_b = await run_groq_chat(
            api_key=groq_key,
            model=model,
            messages=messages_b,
            runner=runner_b,
            system_prompt=sys_b,
            tools=tools_b,
            max_tool_rounds=base_tool_rounds,
            on_event=ev_b,
        )
    else:
        reply_b, log_b, used_b = await run_ollama_chat(
            base_url=ollama_base,
            model=model,
            messages=messages_b,
            runner=runner_b,
            system_prompt=sys_b,
            tools=tools_b,
            max_tool_rounds=base_tool_rounds,
            on_event=ev_b,
        )
    used_model = used_b or used_model

    merged_log: list[dict[str, Any]] = []
    for entry in log_a:
        merged_log.append({"phase": "study_a", **entry})
    for entry in log_b:
        merged_log.append({"phase": "study_b", **entry})

    combined = (
        "(Study ingest: two phases — sandbox, then integrate with memory.)\n\n"
        f"--- Phase A ---\n\n{reply_a}\n\n--- Phase B ---\n\n{reply_b}"
    )
    return {
        "reply": combined,
        "tool_log": merged_log,
        "model": used_model,
        "provider": body.provider,
        "intent": route,
        "intent_source": intent_source,
        "max_tool_rounds": seg_rounds,
        "study_ingest": True,
        "study_session_kind": sk,
        "study_phases": 2,
    }


    return {
        "reply": combined,
        "tool_log": merged_log,
        "model": used_model,
        "provider": body.provider,
        "intent": route,
        "intent_source": intent_source,
        "max_tool_rounds": seg_rounds,
        "study_ingest": True,
        "study_session_kind": sk,
        "study_phases": 2,
    }


async def _resolve_chat_context(
    body: ChatBody,
    store: GraphStore,
    settings: Settings,
) -> tuple[
    list[dict[str, Any]],
    str,
    str,
    str,
    int,
    IntentRoute,
    IntentSource,
]:
    dialogue = _prepare_chat_messages(body, settings)
    model = (
        (body.model or (settings.groq_model if body.provider == "groq" else settings.ollama_model))
        .strip()
        or (settings.groq_model if body.provider == "groq" else settings.ollama_model)
    )
    groq_key = (settings.groq_api_key or "").strip()
    ollama_base = _resolve_base_url(body, settings)
    tool_rounds = _resolve_max_tool_rounds(body, settings)

    if body.provider == "groq" and not groq_key:
        raise HTTPException(
            status_code=503,
            detail="Groq is not configured. Set GROQ_API_KEY in .env (see .env.example).",
        )

    dialogue_for_route = _intent_dialogue_for_long_last_message(dialogue)
    try:
        route, intent_source = await _resolve_intent_route(
            body,
            dialogue=dialogue_for_route,
            settings=settings,
            ollama_base=ollama_base,
            groq_key=groq_key,
            model=model,
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

    return dialogue, model, groq_key, ollama_base, tool_rounds, route, intent_source


async def _run_standard_chat(
    body: ChatBody,
    dialogue: list[dict[str, Any]],
    store: GraphStore,
    settings: Settings,
    *,
    model: str,
    groq_key: str,
    ollama_base: str,
    tool_rounds: int,
    route: IntentRoute,
    intent_source: IntentSource,
    on_event: ChatEventCallback | None = None,
) -> dict[str, Any]:
    runner = MemoryToolRunner(
        store,
        chat_route=route,
        query_field_salience_bump=settings.query_field_salience_bump,
        field_salience_max=settings.field_salience_max,
    )
    tool_defs = tools_for_intent_route(route)
    sys_prompt = build_chat_system_prompt(route)
    fixed_block = _build_system_context_prompt_block(store)
    if fixed_block:
        sys_prompt = f"{sys_prompt}\n\n{fixed_block}"

    if body.provider == "groq":
        try:
            reply, tool_log, used = await run_groq_chat(
                api_key=groq_key,
                model=model,
                messages=dialogue,
                runner=runner,
                system_prompt=sys_prompt,
                tools=tool_defs,
                max_tool_rounds=tool_rounds,
                on_event=on_event,
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

    try:
        reply, tool_log, used = await run_ollama_chat(
            base_url=ollama_base,
            model=model,
            messages=dialogue,
            runner=runner,
            system_prompt=sys_prompt,
            tools=tool_defs,
            max_tool_rounds=tool_rounds,
            on_event=on_event,
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


async def _execute_chat_body(
    body: ChatBody,
    store: GraphStore,
    settings: Settings,
    on_event: ChatEventCallback | None = None,
) -> dict[str, Any]:
    dialogue, model, groq_key, ollama_base, tool_rounds, route, intent_source = await _resolve_chat_context(
        body, store, settings
    )
    if on_event is not None:
        await on_event(
            {
                "type": "intent",
                "route": route,
                "intent_source": intent_source,
            }
        )
    last_full = str(dialogue[-1].get("content") or "")

    if _should_use_study(body, settings, len(last_full), route):
        try:
            return await _chat_study_ingest(
                body,
                dialogue,
                store,
                settings,
                model,
                groq_key,
                ollama_base,
                tool_rounds,
                route,
                intent_source,
                on_event=on_event,
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

    return await _run_standard_chat(
        body,
        dialogue,
        store,
        settings,
        model=model,
        groq_key=groq_key,
        ollama_base=ollama_base,
        tool_rounds=tool_rounds,
        route=route,
        intent_source=intent_source,
        on_event=on_event,
    )


def _sse_frame(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.post("/chat")
async def llm_chat(body: ChatBody, store: GraphStore = Depends(get_graph_store)) -> dict[str, Any]:
    settings = get_settings()
    return await _execute_chat_body(body, store, settings)


@router.post("/chat/stream")
async def llm_chat_stream(body: ChatBody, store: GraphStore = Depends(get_graph_store)) -> StreamingResponse:
    settings = get_settings()
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def on_event(event: dict[str, Any]) -> None:
        await queue.put(event)

    async def producer() -> None:
        try:
            result = await _execute_chat_body(body, store, settings, on_event=on_event)
            await queue.put({"type": "reply", "text": result.get("reply") or ""})
            done_payload = dict(result)
            done_payload["type"] = "done"
            await queue.put(done_payload)
        except HTTPException as e:
            await queue.put({"type": "error", "detail": e.detail, "status": e.status_code})
        except Exception as e:
            await queue.put({"type": "error", "detail": str(e), "status": 500})
        finally:
            await queue.put(None)

    async def event_stream() -> AsyncIterator[str]:
        task = asyncio.create_task(producer())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield _sse_frame(item)
        finally:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/transcribe")
async def transcribe_audio(
    audio: UploadFile = File(..., description="Recorded speech (e.g. webm, wav, mp3, m4a)"),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    """
    Speech-to-text via Groq Whisper (OpenAI-compatible transcription API).
    Requires GROQ_API_KEY on the server; independent of chat provider (Ollama vs Groq).
    """
    raw = await audio.read()
    text = await transcribe_audio_bytes(
        raw,
        filename=audio.filename or "audio.webm",
        content_type=audio.content_type or "application/octet-stream",
        settings=settings,
    )
    return {"text": text}
