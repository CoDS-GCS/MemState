from __future__ import annotations

import os
import tempfile
from pathlib import Path

from memstate.api.ui_graph_payload import build_ui_graph_snapshot
from memstate.llm.chat_api import _build_system_context_prompt_block
from memstate.schema import init_graph
from memstate.store.graph_store import GraphStore
from memstate.store.kuzu_adapter import KuzuGraph, clear_kuzu_graph_cache


def _fresh_store() -> GraphStore:
    fd, path = tempfile.mkstemp(suffix=".kuzu")
    os.close(fd)
    clear_kuzu_graph_cache()
    g = KuzuGraph(str(Path(path).resolve()))
    init_graph(g)
    return GraphStore(g)


def test_system_context_roundtrip_and_prompt_block() -> None:
    store = _fresh_store()
    row = store.set_system_config(
        system_role="Tutor assistant",
        runtime_context="Runs in a student study app.",
        updated_by="test",
    )
    assert row["system_role"] == "Tutor assistant"
    assert row["runtime_context"] == "Runs in a student study app."
    block = _build_system_context_prompt_block(store)
    assert "Tutor assistant" in block
    assert "student study app" in block


def test_system_context_not_in_graph_nodes() -> None:
    store = _fresh_store()
    store.set_system_config(system_role="Role", runtime_context="Ctx")
    snap = build_ui_graph_snapshot(store)
    assert snap["nodes"] == []
    assert snap["edges"] == []
