"""Study hierarchy and sandbox tool rules."""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

from memstate.llm.study_hierarchy import build_study_hierarchy, study_topic_kind
from memstate.llm.tool_runner import MemoryToolRunner
from memstate.schema import init_graph
from memstate.store.graph_store import GraphStore
from memstate.store.kuzu_adapter import KuzuGraph, clear_kuzu_graph_cache


def test_build_study_hierarchy_plain_paragraphs() -> None:
    doc = "First paragraph one.\n\nSecond paragraph two. More here.\n\nThird."
    h = build_study_hierarchy(doc)
    assert h.session_id
    assert len(h.units) >= 3
    coarse = [u for u in h.units if u.level == 0]
    assert len(coarse) >= 1
    assert all(u.token_count >= 0 for u in h.units)


def test_build_study_hierarchy_markdown_headings() -> None:
    doc = "# Title\n\nIntro sentence.\n\n## Sub\n\nDetail one. Detail two."
    h = build_study_hierarchy(doc)
    assert any(u.level == 0 for u in h.units)


def test_study_topic_kind_format() -> None:
    sid = str(uuid.uuid4())
    assert study_topic_kind(sid) == f"study:{sid}"


def _fresh_store() -> GraphStore:
    fd, path = tempfile.mkstemp(suffix=".kuzu")
    os.close(fd)
    clear_kuzu_graph_cache()
    g = KuzuGraph(str(Path(path).resolve()))
    init_graph(g)
    return GraphStore(g)


def test_study_runner_list_and_create() -> None:
    store = _fresh_store()
    sid = str(uuid.uuid4())
    sk = study_topic_kind(sid)
    r = MemoryToolRunner(store, study_session_kind=sk, study_catalog={"session_id": sid, "units": []})
    out = r.execute("memory_list_topics", {})
    assert out["ok"] is True
    assert out["topics"] == []
    c = r.execute("memory_create_topic", {"title": "A", "summary": "s"})
    assert c["ok"] is True
    tid = c["topic_id"]
    row = store.get_topic(tid)
    assert row and str(row.get("topic_kind")) == sk


def test_study_runner_rejects_cross_session_edge() -> None:
    store = _fresh_store()
    sid = str(uuid.uuid4())
    sk = study_topic_kind(sid)
    r = MemoryToolRunner(store, study_session_kind=sk)
    tid_in = r.execute("memory_create_topic", {"title": "in"})["topic_id"]
    other = str(uuid.uuid4())
    store.create_topic(
        other,
        title="other",
        summary=None,
        salience=1.0,
        archived=False,
        embedding=None,
        topic_kind="notes",
    )
    bad = r.execute(
        "memory_add_relationship",
        {"from_topic_id": tid_in, "to_topic_id": other, "kind": "RELATED"},
    )
    assert bad["ok"] is False


def test_study_runner_rejects_nested_study_child() -> None:
    store = _fresh_store()
    sid = str(uuid.uuid4())
    sk = study_topic_kind(sid)
    r = MemoryToolRunner(store, study_session_kind=sk)
    pa = r.execute("memory_create_topic", {"title": "p"})["topic_id"]
    ch = r.execute("memory_create_topic", {"title": "c"})["topic_id"]
    ok = r.execute(
        "memory_add_relationship",
        {"from_topic_id": pa, "to_topic_id": ch, "kind": "study_child"},
    )
    assert ok["ok"] is True
    gc = r.execute("memory_create_topic", {"title": "gc"})["topic_id"]
    bad = r.execute(
        "memory_add_relationship",
        {"from_topic_id": ch, "to_topic_id": gc, "kind": "study_child"},
    )
    assert bad["ok"] is False
