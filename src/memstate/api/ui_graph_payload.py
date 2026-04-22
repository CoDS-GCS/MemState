"""Shared graph snapshot for the dev UI and LLM tools (same JSON shape)."""

from __future__ import annotations

from typing import Any

from memstate.api.graph_viz_communities import compute_topic_communities
from memstate.datamodel.fields import (
    TopicField,
    TopicFields,
    is_nested_fields_bundle_value,
    nested_bundle_inner_fields,
)
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
            row_fs: dict[str, Any] = {
                "name": name,
                "field_type": rec.field_type,
                "ref_topic_id": rec.ref_topic_id,
                "current_value": cur.value if cur else None,
                "history_len": len(rec.history),
            }
            if rec.field_type == "json" and cur and is_nested_fields_bundle_value(cur.value):
                inner = nested_bundle_inner_fields(cur.value)
                nested_fields: list[dict[str, Any]] = []
                for sub_name in sorted(inner.keys()):
                    sub_raw = inner.get(sub_name)
                    if isinstance(sub_raw, dict):
                        try:
                            srec = TopicField.model_validate(sub_raw)
                            sce = srec.current_entry()
                            nested_fields.append(
                                {
                                    "name": sub_name,
                                    "field_type": srec.field_type,
                                    "current_value": sce.value if sce else None,
                                    "history_len": len(srec.history),
                                }
                            )
                        except Exception:
                            nested_fields.append(
                                {
                                    "name": sub_name,
                                    "field_type": "string",
                                    "current_value": None,
                                    "history_len": 0,
                                }
                            )
                row_fs["nested_fields"] = nested_fields
                for sub_name, sub_raw in inner.items():
                    if not isinstance(sub_raw, dict):
                        continue
                    try:
                        srec = TopicField.model_validate(sub_raw)
                    except Exception:
                        continue
                    if srec.ref_topic_id:
                        rid = str(srec.ref_topic_id)
                        edges.append(
                            {
                                "from": sid,
                                "to": rid,
                                "kind": f"field:{name}.{sub_name}",
                                "edge_type": "field_ref",
                            }
                        )
                        add_structural(sid, rid)
            fields_summary.append(row_fs)
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
                "summary": row.get("summary") or "",
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


def topic_schema_struct_from_row(row: dict[str, Any]) -> dict[str, Any] | None:
    """One topic’s schema-only payload (field names/types/refs/salience; nested bundle names). No values/history."""
    if not row:
        return None
    sid = str(row.get("id") or "")
    if not sid:
        return None
    tf = TopicFields.from_json(row.get("fields_json") if isinstance(row.get("fields_json"), str) else "")
    fields_out: dict[str, Any] = {}
    for fname, rec in tf.fields.items():
        telem: dict[str, Any] = {
            "field_type": rec.field_type,
            "ref_topic_id": rec.ref_topic_id,
            "salience": rec.salience,
        }
        cur = rec.current_entry()
        if rec.field_type == "json" and cur and is_nested_fields_bundle_value(cur.value):
            telem["nested_field_names"] = sorted(nested_bundle_inner_fields(cur.value).keys())
        fields_out[fname] = telem
    tk = row.get("topic_kind")
    return {
        "id": sid,
        "title": str(row.get("title") or ""),
        "topic_kind": str(tk) if tk else "",
        "archived": bool(row.get("archived")),
        "salience": float(row.get("salience") or 0),
        "fields": fields_out,
        "field_count": len(fields_out),
    }


def build_topics_schema_page(
    store: GraphStore,
    *,
    offset: int = 0,
    limit: int = 15,
    include_archived: bool = False,
    topic_kind: str | None = None,
) -> dict[str, Any]:
    """
    Paginated schema-only view for iterating topics without loading values or the full snapshot.
    Stable order: sorted topic id. ``limit`` is capped at 50.
    """
    all_ids = store.list_topic_ids(include_archived=include_archived, topic_kind=topic_kind)
    all_ids_sorted = sorted(all_ids)
    total = len(all_ids_sorted)
    off = max(0, int(offset))
    lim = max(1, min(int(limit), 50))
    page_ids = all_ids_sorted[off : off + lim]
    topics: list[dict[str, Any]] = []
    for tid in page_ids:
        row = store.get_topic(tid)
        if not row:
            continue
        payload = topic_schema_struct_from_row(row)
        if payload:
            topics.append(payload)
    has_more = off + lim < total
    return {
        "topics": topics,
        "offset": off,
        "limit": lim,
        "total": total,
        "has_more": has_more,
        "next_offset": (off + lim) if has_more else None,
    }


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
        payload = topic_schema_struct_from_row(row)
        if payload:
            # Snapshot historically omitted field_count; strip for identical wire shape
            pl = {k: v for k, v in payload.items() if k != "field_count"}
            topics.append(pl)

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
