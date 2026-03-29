"""Study hierarchy and sandbox tool rules."""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

from memstate.datamodel.fields import TopicFields, is_nested_fields_bundle_value, new_history_entry
from memstate.api.ui_graph_payload import build_topics_schema_page
from memstate.llm.study_hierarchy import build_study_hierarchy, study_topic_kind
from memstate.llm.tool_runner import MemoryToolRunner
from memstate.schema import init_graph
from memstate.store.graph_store import GraphStore
from memstate.store.kuzu_adapter import KuzuGraph, clear_kuzu_graph_cache


def test_topics_schema_page_pagination() -> None:
    store = _fresh_store()
    for i in range(3):
        tid = str(uuid.uuid4())
        store.create_topic(tid, title=f"T{i}", summary=None, salience=1.0, archived=False, embedding=None)
        store.append_field_history(
            tid,
            "a",
            new_history_entry(value=str(i), valid_from="2026-01-01T00:00:00+00:00", provenance="t"),
        )
    p0 = build_topics_schema_page(store, offset=0, limit=2)
    assert p0["total"] == 3
    assert len(p0["topics"]) == 2
    assert p0["has_more"] is True
    assert p0["next_offset"] == 2
    p1 = build_topics_schema_page(store, offset=2, limit=2)
    assert len(p1["topics"]) == 1
    assert p1["has_more"] is False
    assert p1["next_offset"] is None


def test_memory_topics_schema_page_runner() -> None:
    store = _fresh_store()
    tid = str(uuid.uuid4())
    store.create_topic(tid, title="One", summary=None, salience=1.0, archived=False, embedding=None)
    r = MemoryToolRunner(store)
    out = r.execute("memory_topics_schema_page", {"offset": 0, "limit": 10})
    assert out["ok"] is True
    assert out["total"] == 1
    assert len(out["topics"]) == 1
    assert out["topics"][0]["id"] == tid
    assert "field_count" in out["topics"][0]


def test_study_runner_topics_schema_page_session_only() -> None:
    store = _fresh_store()
    sid = str(uuid.uuid4())
    sk = study_topic_kind(sid)
    r = MemoryToolRunner(store, study_session_kind=sk)
    r.execute("memory_create_topic", {"title": "in"})
    other = str(uuid.uuid4())
    store.create_topic(
        other,
        title="out",
        summary=None,
        salience=1.0,
        archived=False,
        embedding=None,
        topic_kind="notes",
    )
    out = r.execute("memory_topics_schema_page", {})
    assert out["ok"] is True
    assert out["total"] == 1
    assert out["topics"][0]["title"] == "in"


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


def test_promote_fields_to_nested_topic_store() -> None:
    store = _fresh_store()
    pid = str(uuid.uuid4())
    store.create_topic(
        pid,
        title="Parent",
        summary=None,
        salience=1.0,
        archived=False,
        embedding=None,
        topic_kind="person",
    )
    store.append_field_history(
        pid,
        "role",
        new_history_entry(value="dev", valid_from="2026-01-01T00:00:00+00:00", provenance="t"),
    )
    store.append_field_history(
        pid,
        "employer",
        new_history_entry(value="Acme", valid_from="2026-01-02T00:00:00+00:00", provenance="t"),
    )
    out = store.promote_fields_to_nested_topic(
        pid,
        ["role", "employer"],
        "Work",
        parent_link_field="work_detail",
        relationship_kind="has_detail",
    )
    cid = out["child_topic_id"]
    parent = store.get_topic(pid)
    child = store.get_topic(cid)
    assert parent and child
    assert str(child.get("title")) == "Work"
    pfields = TopicFields.from_json(parent.get("fields_json") if isinstance(parent.get("fields_json"), str) else "")
    cfields = TopicFields.from_json(child.get("fields_json") if isinstance(child.get("fields_json"), str) else "")
    assert "role" not in pfields.fields and "employer" not in pfields.fields
    assert "role" in cfields.fields and "employer" in cfields.fields
    assert cfields.fields["role"].history[0].value == "dev"
    assert "work_detail" in pfields.fields
    assert pfields.fields["work_detail"].ref_topic_id == cid
    link = pfields.fields["work_detail"].current_entry()
    assert link is not None
    assert link.operation == "nested_topic_link"
    rels = store.list_relationships(pid, direction="out")
    assert any(str(r.get("id")) == cid and str(r.get("kind")) == "has_detail" for r in rels)


def test_nest_and_unnest_fields_same_topic() -> None:
    store = _fresh_store()
    pid = str(uuid.uuid4())
    store.create_topic(pid, title="P", summary=None, salience=1.0, archived=False, embedding=None)
    store.append_field_history(
        pid,
        "a",
        new_history_entry(value="1", valid_from="2026-01-01T00:00:00+00:00", provenance="t"),
    )
    store.append_field_history(
        pid,
        "b",
        new_history_entry(value="2", valid_from="2026-01-02T00:00:00+00:00", provenance="t"),
    )
    store.nest_fields_in_topic(pid, ["a", "b"], "grp", provenance="t")
    row = store.get_topic(pid)
    assert row
    tf = TopicFields.from_json(row.get("fields_json") if isinstance(row.get("fields_json"), str) else "")
    assert "a" not in tf.fields and "b" not in tf.fields and "grp" in tf.fields
    cur = tf.fields["grp"].current_entry()
    assert cur is not None and is_nested_fields_bundle_value(cur.value)
    store.unnest_fields_in_topic(pid, "grp")
    row2 = store.get_topic(pid)
    assert row2
    tf2 = TopicFields.from_json(row2.get("fields_json") if isinstance(row2.get("fields_json"), str) else "")
    assert "a" in tf2.fields and "b" in tf2.fields and "grp" not in tf2.fields


def test_memory_nest_fields_runner() -> None:
    store = _fresh_store()
    pid = str(uuid.uuid4())
    store.create_topic(pid, title="P", summary=None, salience=1.0, archived=False, embedding=None)
    r = MemoryToolRunner(store)
    r.execute(
        "memory_append_field",
        {"topic_id": pid, "field_name": "x", "value": "v"},
    )
    out = r.execute(
        "memory_nest_fields_in_topic",
        {"topic_id": pid, "field_names": ["x"], "nest_key": "bundle"},
    )
    assert out["ok"] is True
    un = r.execute("memory_unnest_fields_in_topic", {"topic_id": pid, "nest_key": "bundle"})
    assert un["ok"] is True


def test_undo_promote_nested_topic_store() -> None:
    store = _fresh_store()
    pid = str(uuid.uuid4())
    store.create_topic(
        pid,
        title="Parent",
        summary=None,
        salience=1.0,
        archived=False,
        embedding=None,
    )
    store.append_field_history(
        pid,
        "a",
        new_history_entry(value="1", valid_from="2026-01-01T00:00:00+00:00", provenance="t"),
    )
    out = store.promote_fields_to_nested_topic(
        pid,
        ["a"],
        "Nested",
        relationship_kind="has_detail",
    )
    cid = out["child_topic_id"]
    u = store.undo_promote_nested_topic(pid, cid, relationship_kind="has_detail")
    assert u["restored_fields"] == ["a"]
    assert u["deleted_child_topic_id"] == cid
    assert not store.topic_exists(cid)
    prow = store.get_topic(pid)
    assert prow
    pfields = TopicFields.from_json(prow.get("fields_json") if isinstance(prow.get("fields_json"), str) else "")
    assert "a" in pfields.fields
    assert pfields.fields["a"].history[0].value == "1"
    rels = store.list_relationships(pid, direction="out")
    assert not any(str(r.get("id")) == cid for r in rels)


def test_memory_undo_promote_nested_topic_runner() -> None:
    store = _fresh_store()
    pid = str(uuid.uuid4())
    store.create_topic(pid, title="P", summary=None, salience=1.0, archived=False, embedding=None)
    store.append_field_history(
        pid,
        "x",
        new_history_entry(value="v", valid_from="2026-01-01T00:00:00+00:00", provenance="t"),
    )
    r = MemoryToolRunner(store)
    pr = r.execute(
        "memory_promote_fields_to_nested_topic",
        {"parent_topic_id": pid, "field_names": ["x"], "child_title": "C"},
    )
    assert pr["ok"] is True
    cid = pr["child_topic_id"]
    un = r.execute("memory_undo_promote_nested_topic", {"parent_topic_id": pid, "child_topic_id": cid})
    assert un["ok"] is True
    assert not store.topic_exists(cid)


def test_study_runner_promote_nested_topic() -> None:
    store = _fresh_store()
    sid = str(uuid.uuid4())
    sk = study_topic_kind(sid)
    r = MemoryToolRunner(store, study_session_kind=sk)
    pid = r.execute("memory_create_topic", {"title": "Section"})["topic_id"]
    r.execute("memory_append_field", {"topic_id": pid, "field_name": "note", "value": "alpha"})
    out = r.execute(
        "memory_promote_fields_to_nested_topic",
        {
            "parent_topic_id": pid,
            "field_names": ["note"],
            "child_title": "Detail",
            "relationship_kind": "study_child",
        },
    )
    assert out["ok"] is True
    cid = out["child_topic_id"]
    child = store.get_topic(cid)
    assert child and str(child.get("topic_kind")) == sk
    prow = store.get_topic(pid)
    assert prow
    pfields = TopicFields.from_json(prow.get("fields_json") if isinstance(prow.get("fields_json"), str) else "")
    assert "note" not in pfields.fields
