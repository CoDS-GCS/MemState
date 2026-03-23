"""HTTP API for LLM chat (Ollama + memory tools)."""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from memstate.api.deps import get_graph_store
from memstate.config import get_settings
from memstate.llm.ollama_chat import run_ollama_chat
from memstate.llm.tool_runner import MemoryToolRunner
from memstate.store.graph_store import GraphStore

router = APIRouter(prefix="/api/llm", tags=["llm"])


class ChatBody(BaseModel):
    messages: list[dict[str, Any]] = Field(
        ...,
        description="OpenAI-style messages (typically user/assistant turns; system is added server-side).",
    )
    model: str | None = Field(None, description="Override MEMSTATE_OLLAMA_MODEL")


@router.post("/chat")
async def llm_chat(body: ChatBody, store: GraphStore = Depends(get_graph_store)) -> dict[str, Any]:
    settings = get_settings()
    model = body.model or settings.ollama_model
    base = settings.ollama_base_url
    runner = MemoryToolRunner(store)
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
            detail=f"Cannot reach Ollama at {base}. Start Ollama or set MEMSTATE_OLLAMA_BASE_URL. ({e})",
        ) from e

    return {
        "reply": reply,
        "tool_log": tool_log,
        "model": used,
    }
