"""HTTP API for LLM chat (Ollama + Groq + memory tools)."""

from __future__ import annotations

from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from memstate.api.deps import get_graph_store
from memstate.config import Settings, get_settings
from memstate.llm.groq_chat import run_groq_chat
from memstate.llm.ollama_chat import run_ollama_chat
from memstate.llm.ollama_url import normalize_ollama_base_url, validate_client_ollama_url
from memstate.llm.tool_runner import MemoryToolRunner
from memstate.store.graph_store import GraphStore

router = APIRouter(prefix="/api/llm", tags=["llm"])


class ChatBody(BaseModel):
    messages: list[dict[str, Any]] = Field(
        ...,
        description="OpenAI-style messages (typically user/assistant turns; system is added server-side).",
    )
    provider: Literal["ollama", "groq"] = "ollama"
    model: str | None = Field(None, description="Model id (provider-specific)")
    ollama_base_url: str | None = Field(
        None,
        description="Override Ollama API base (Ollama provider only).",
    )


def _resolve_base_url(body: ChatBody, settings: Settings) -> str:
    if body.ollama_base_url and body.ollama_base_url.strip():
        return validate_client_ollama_url(body.ollama_base_url, settings)
    try:
        return normalize_ollama_base_url(settings.ollama_base_url)
    except ValueError:
        return settings.ollama_base_url.rstrip("/")


@router.post("/chat")
async def llm_chat(body: ChatBody, store: GraphStore = Depends(get_graph_store)) -> dict[str, Any]:
    settings = get_settings()
    runner = MemoryToolRunner(store)

    if body.provider == "groq":
        key = (settings.groq_api_key or "").strip()
        if not key:
            raise HTTPException(
                status_code=503,
                detail="Groq is not configured. Set GROQ_API_KEY in .env (see .env.example).",
            )
        model = (body.model or settings.groq_model).strip() or settings.groq_model
        try:
            reply, tool_log, used = await run_groq_chat(
                api_key=key,
                model=model,
                messages=body.messages,
                runner=runner,
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
        }

    # Ollama
    model = (body.model or settings.ollama_model).strip() or settings.ollama_model
    base = _resolve_base_url(body, settings)
    try:
        reply, tool_log, used = await run_ollama_chat(
            base_url=base,
            model=model,
            messages=body.messages,
            runner=runner,
        )
    except httpx.HTTPStatusError as e:
        detail = e.response.text if e.response is not None else str(e)
        raise HTTPException(status_code=502, detail=f"Ollama error: {detail}") from e
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Cannot reach Ollama at {base}. "
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
    }
