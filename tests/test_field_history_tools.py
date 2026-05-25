"""Field read tools return current value and revision history."""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

from memstate.datamodel.fields import new_history_entry
from memstate.llm.tool_runner import MemoryToolRunner
from memstate.llm.tools_schema import QUERY_TOOL_NAMES, tools_for_intent_route
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


def test_memory_get_field_returns_value_and_history() -> None:
    store = _fresh_store()
    tid = str(uuid.uuid4())
    store.create_topic(tid, title="Person", summary=None, salience=1.0, archived=False, embedding=None)
    store.append_field_history(
        tid,
        "city",
        new_history_entry(value="Ottawa", valid_from="2026-01-01T00:00:00+00:00", provenance="t"),
    )
    store.append_field_history(
        tid,
        "city",
        new_history_entry(value="Toronto", valid_from="2026-05-01T00:00:00+00:00", provenance="t"),
    )
    r = MemoryToolRunner(store)
    out = r.execute("memory_get_field", {"topic_id": tid, "field_name": "city"})
    assert out["ok"] is True
    field = out["field"]
    assert field["value"] == "Toronto"
    assert field["history_count"] == 2
    assert len(field["history"]) == 2
    assert field["history"][0]["value"] == "Toronto"
    assert field["history"][1]["value"] == "Ottawa"


def test_memory_get_field_without_history() -> None:
    store = _fresh_store()
    tid = str(uuid.uuid4())
    store.create_topic(tid, title="Person", summary=None, salience=1.0, archived=False, embedding=None)
    store.append_field_history(
        tid,
        "city",
        new_history_entry(value="Toronto", valid_from="2026-05-01T00:00:00+00:00", provenance="t"),
    )
    r = MemoryToolRunner(store)
    out = r.execute(
        "memory_get_field",
        {"topic_id": tid, "field_name": "city", "with_history": False},
    )
    assert out["ok"] is True
    field = out["field"]
    assert field["value"] == "Toronto"
    assert "history" not in field
    assert "history_count" not in field


def test_memory_get_field_history_tool() -> None:
    store = _fresh_store()
    tid = str(uuid.uuid4())
    store.create_topic(tid, title="Person", summary=None, salience=1.0, archived=False, embedding=None)
    store.append_field_history(
        tid,
        "city",
        new_history_entry(value="Ottawa", valid_from="2026-01-01T00:00:00+00:00", provenance="t"),
    )
    store.append_field_history(
        tid,
        "city",
        new_history_entry(value="Toronto", valid_from="2026-05-01T00:00:00+00:00", provenance="t"),
    )
    r = MemoryToolRunner(store)
    out = r.execute("memory_get_field_history", {"topic_id": tid, "field_name": "city"})
    assert out["ok"] is True
    assert out["topic_id"] == tid
    assert out["field_name"] == "city"
    field = out["field"]
    assert field["value"] == "Toronto"
    assert field["history_count"] == 2


def test_query_route_exposes_field_history_tool() -> None:
    names = {t["function"]["name"] for t in tools_for_intent_route("query")}
    assert "memory_get_field_history" in names
    assert "memory_get_field_history" in QUERY_TOOL_NAMES
