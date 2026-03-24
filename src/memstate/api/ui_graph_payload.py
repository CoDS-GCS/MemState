"""Shared graph snapshot for the dev UI and LLM tools (same JSON shape)."""

from __future__ import annotations

from typing import Any

from memstate.api.graph_viz_communities import compute_topic_communities
from memstate.datamodel.fields import TopicFields
from memstate.datamodel.mappers import topic_from_graph_row
from memstate.store.graph_store import GraphStore


def build_ui_graph_snapshot(store: GraphStore) -> dict[str, Any]:
    """
    Return ``{ "nodes": [...], "edges": [...] }`` for visualization and tools.

    Each node includes ``community``: clusters merge (1) undirected structural
    edges — field refs and RELATED — with (2) cosine-similarity neighborhoods
    between topic embeddings (see :func:`compute_topic_communities`).
    """
    topic_ids = store.list_topic_ids(include_archived=True)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    seen_rel: set[tuple[str, str, str]] = set()
    structural: set[tuple[str, str]] = set()
    embeddings: dict[str, list[float]] = {}

    def add_structural(a: str, b: str) -> None:
        if not a or not b or a == b:
            return
        structural.add((a, b) if a < b else (b, a))

    for tid in topic_ids:
        row = store.get_topic(tid)
        if not row:
            continue
        sid = str(tid)
        topic_node = topic_from_graph_row(row)
        if topic_node and topic_node.embedding:
            embeddings[sid] = list(topic_node.embedding)

        tf = TopicFields.from_json(row.get("fields_json") if isinstance(row.get("fields_json"), str) else "")
        fields_summary: list[dict[str, Any]] = []
        for name, rec in tf.fields.items():
            cur = rec.current_entry()
            fields_summary.append(
                {
                    "name": name,
                    "field_type": rec.field_type,
                    "ref_topic_id": rec.ref_topic_id,
                    "current_value": cur.value if cur else None,
                    "history_len": len(rec.history),
                }
            )
            if rec.ref_topic_id:
                rid = str(rec.ref_topic_id)
                edges.append(
                    {
                        "from": sid,
                        "to": rid,
                        "kind": f"field:{name}",
                        "edge_type": "field_ref",
                    }
                )
                add_structural(sid, rid)

        tk = row.get("topic_kind")
        nodes.append(
            {
                "id": sid,
                "label": str(row.get("title") or sid)[:80],
                "title": row.get("title") or "",
                "topic_kind": str(tk) if tk else "",
                "archived": bool(row.get("archived")),
                "salience": float(row.get("salience") or 0),
                "fields": fields_summary,
            }
        )

        for r in store.list_relationships(tid, direction="out"):
            to_id = str(r.get("id") or "")
            kind = str(r.get("kind") or "")
            key = (sid, to_id, kind)
            if key in seen_rel:
                continue
            seen_rel.add(key)
            edges.append(
                {
                    "from": sid,
                    "to": to_id,
                    "kind": kind,
                    "edge_type": "related",
                }
            )
            add_structural(sid, to_id)

    comm = compute_topic_communities(
        [n["id"] for n in nodes],
        list(structural),
        embeddings,
    )
    for n in nodes:
        n["community"] = int(comm.get(n["id"], 0))

    return {"nodes": nodes, "edges": edges}


def build_study_graph_snapshot(store: GraphStore, study_topic_kind: str) -> dict[str, Any]:
    """
    Same shape as :func:`build_ui_graph_snapshot`, but only topics with the given
    ``topic_kind`` (e.g. ``study:<session_uuid>``) and edges between those topics only.
    """
    tk = str(study_topic_kind).strip()
    topic_ids = store.list_topic_ids(include_archived=True, topic_kind=tk)
    allowed = set(topic_ids)
    if not allowed:
        return {"nodes": [], "edges": []}
    full = build_ui_graph_snapshot(store)
    nodes = [n for n in full.get("nodes", []) if n.get("id") in allowed]
    edges = [
        e for e in full.get("edges", []) if e.get("from") in allowed and e.get("to") in allowed
    ]
    # Recompute community only on subgraph nodes (structural edges among allowed).
    structural: set[tuple[str, str]] = set()
    for e in edges:
        a, b = str(e.get("from")), str(e.get("to"))
        if a and b and a != b:
            structural.add((a, b) if a < b else (b, a))
    embeddings: dict[str, list[float]] = {}
    for n in nodes:
        sid = str(n["id"])
        row = store.get_topic(sid)
        if row and row.get("embedding"):
            emb = row.get("embedding")
            if isinstance(emb, list) and emb:
                embeddings[sid] = [float(x) for x in emb]
    comm = compute_topic_communities(
        [n["id"] for n in nodes],
        list(structural),
        embeddings,
    )
    for n in nodes:
        n["community"] = int(comm.get(n["id"], 0))
    return {"nodes": nodes, "edges": edges}


def build_topics_schema_snapshot(store: GraphStore) -> dict[str, Any]:
    """
    Structural view for reorganization: topic id, title, kind, salience, archived,
    and per-field ``field_type``, ``ref_topic_id``, ``salience`` only.

    Omits topic summaries, field values, and revision history. RELATED edges only
    (no field_ref duplicate edges—refs appear on fields).
    """
    topic_ids = store.list_topic_ids(include_archived=True)
    topics: list[dict[str, Any]] = []
    for tid in topic_ids:
        row = store.get_topic(tid)
        if not row:
            continue
        sid = str(tid)
        tf = TopicFields.from_json(row.get("fields_json") if isinstance(row.get("fields_json"), str) else "")
        fields_out: dict[str, Any] = {}
        for fname, rec in tf.fields.items():
            fields_out[fname] = {
                "field_type": rec.field_type,
                "ref_topic_id": rec.ref_topic_id,
                "salience": rec.salience,
            }
        tk = row.get("topic_kind")
        topics.append(
            {
                "id": sid,
                "title": str(row.get("title") or ""),
                "topic_kind": str(tk) if tk else "",
                "archived": bool(row.get("archived")),
                "salience": float(row.get("salience") or 0),
                "fields": fields_out,
            }
        )

    edges: list[dict[str, Any]] = []
    seen_rel: set[tuple[str, str, str]] = set()
    for tid in topic_ids:
        sid = str(tid)
        for r in store.list_relationships(tid, direction="out"):
            to_id = str(r.get("id") or "")
            kind = str(r.get("kind") or "")
            key = (sid, to_id, kind)
            if key in seen_rel:
                continue
            seen_rel.add(key)
            edges.append(
                {
                    "from": sid,
                    "to": to_id,
                    "kind": kind,
                    "edge_type": "related",
                }
            )

    return {"topics": topics, "edges": edges}
