"""Execute memory tool calls against GraphStore (shared by HTTP chat and MCP)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from memstate.api.ui_graph_payload import build_topics_schema_snapshot, build_ui_graph_snapshot
from memstate.datamodel.fields import TopicField, TopicFields, new_history_entry
from memstate.llm.tools_schema import IntentRoute
from memstate.store.graph_store import REF_UNCHANGED, GraphStore


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _graph_snapshot(store: GraphStore) -> dict[str, Any]:
    """Same shape as GET /api/ui/graph (includes ``community`` per node)."""
    return build_ui_graph_snapshot(store)


def _topics_schema_snapshot(store: GraphStore) -> dict[str, Any]:
    """Field names/types/refs and topic metadata—no values or histories."""
    return build_topics_schema_snapshot(store)


_REORGANIZE_GUIDELINES: dict[str, str] = {
    "consolidation": (
        "Consolidation (schema-first): use only topics_schema_snapshot—field names, types, ref_topic_id, "
        "salience, RELATED edges. No field values or histories are included. Merge synonymous or duplicate "
        "field names, align types, dedupe ref_topic_id targets, remove redundant RELATED edges. Call "
        "memory_get_topic_schema (detail current/history) or memory_get_topic only when you must read values "
        "before writing."
    ),
    "merge_topics": (
        "Merge topics (schema, then values, then judgment): (1) From topics_schema_snapshot, spot candidates—"
        "overlapping field names/types, same topic_kind, similar titles, aligned ref_topic_id patterns, RELATED "
        "neighbors. (2) For each candidate pair or small cluster, load current values with memory_get_topic_schema "
        "detail current (or memory_get_topic). Compare **values**: identical or overlapping strings; list/set "
        "intersection (shared names, repeated items); same refs; duplicate facts about one entity. Strong value "
        "overlap or intersection often means the same real-world subject—merge may help. (3) **Merge only when** "
        "combining topics improves memory organization (less duplication, clearer navigation, one coherent entity). "
        "Do **not** merge distinct people, projects, or themes that merely share a field type or a generic word. "
        "(4) Pick a survivor topic, move/append fields safely, rewire refs and RELATED edges, delete merged ids "
        "only when nothing points to them."
    ),
    "split_topics": (
        "Split topics (schema-first): find topics whose fields partition into disjoint name clusters or mixed "
        "kinds. Plan new topics from structure; use read tools when moving values. Add RELATED between split "
        "parts as appropriate."
    ),
    "connect_topics": (
        "Connect topics (schema-first): use RELATED edges list and field ref_topic_id in the snapshot. Add "
        "RELATED where the schema suggests a missing link between topics (e.g. same kind, complementary field "
        "names) but the graph is disconnected; avoid cluttering."
    ),
    "retention_trim": (
        "Retention trim / RTC (schema-first): use topic archived flag, salience, and field counts/types only. "
        "Archive or lower salience on sparse or low-salience topics; drop empty or redundant fields when safe. "
        "Use memory_get_topic_schema history only if trimming history is required."
    ),
}

_REORGANIZE_TOOL_TO_OP: dict[str, str] = {
    "memory_reorganize_consolidation": "consolidation",
    "memory_reorganize_merge_topics": "merge_topics",
    "memory_reorganize_split_topics": "split_topics",
    "memory_reorganize_connect_topics": "connect_topics",
    "memory_reorganize_retention_trim": "retention_trim",
}


def _fields_schema_payload(tf: TopicFields, *, detail: str) -> dict[str, Any]:
    """Build per-field payload for memory_get_topic_schema (detail: minimal | current | history)."""
    out: dict[str, Any] = {}
    d = (detail or "minimal").strip().lower()
    if d not in ("minimal", "current", "history"):
        d = "minimal"
    for fname, rec in tf.fields.items():
        if d == "minimal":
            out[fname] = {
                "field_type": rec.field_type,
                "ref_topic_id": rec.ref_topic_id,
                "salience": rec.salience,
            }
        elif d == "current":
            cur = rec.current_entry()
            out[fname] = {
                "field_type": rec.field_type,
                "ref_topic_id": rec.ref_topic_id,
                "salience": rec.salience,
                "value": cur.value if cur else None,
            }
        else:
            out[fname] = {
                "field_type": rec.field_type,
                "ref_topic_id": rec.ref_topic_id,
                "salience": rec.salience,
                "history": [e.model_dump() for e in rec.history],
            }
    return out


def _parse_args(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}


def _field_to_topic_out(rec: TopicField) -> dict[str, Any]:
    return {
        "field_type": rec.field_type,
        "ref_topic_id": rec.ref_topic_id,
        "salience": rec.salience,
        "history": [e.model_dump() for e in rec.history],
    }


class MemoryToolRunner:
    def __init__(
        self,
        store: GraphStore,
        *,
        chat_route: IntentRoute | None = None,
        query_field_salience_bump: float = 0.1,
        field_salience_max: float = 10.0,
    ) -> None:
        self._store = store
        self._chat_route = chat_route
        self._query_bump = query_field_salience_bump
        self._field_salience_max = field_salience_max

    def _bump_read_access_salience(self, topic_id: str, field_names: list[str]) -> None:
        """Raise field salience after read tools when chat was routed as query or both (not ingest-only)."""
        if self._chat_route not in ("query", "both") or not field_names:
            return
        self._store.bump_field_salience_on_query(
            topic_id,
            field_names,
            bump=self._query_bump,
            max_field_salience=self._field_salience_max,
        )

    def execute(self, name: str, arguments: Any) -> dict[str, Any]:
        args = _parse_args(arguments)
        try:
            return self._dispatch(name, args)
        except Exception as e:
            return {"ok": False, "error": str(e), "tool": name}

    def _dispatch(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        s = self._store

        if name == "memory_graph_snapshot":
            return {"ok": True, "data": _graph_snapshot(s)}

        if name == "memory_list_topics":
            inc = bool(args.get("include_archived", False))
            topics = s.list_topics_meta(include_archived=inc)
            return {
                "ok": True,
                "topics": topics,
                "topic_ids": [t["id"] for t in topics],
            }

        if name == "memory_get_topic_schema":
            tid = str(args.get("topic_id") or "")
            if not tid:
                return {"ok": False, "error": "topic_id required"}
            row = s.get_topic(tid)
            if not row:
                return {"ok": False, "error": "topic not found"}
            detail = str(args.get("detail") or "minimal").strip().lower()
            if detail not in ("minimal", "current", "history"):
                detail = "minimal"
            tf = TopicFields.from_json(row.get("fields_json") if isinstance(row.get("fields_json"), str) else "")
            names = list(tf.fields.keys())
            self._bump_read_access_salience(tid, names)
            row = s.get_topic(tid)
            tf = TopicFields.from_json(row.get("fields_json") if isinstance(row.get("fields_json"), str) else "")
            fields = _fields_schema_payload(tf, detail=detail)
            return {
                "ok": True,
                "topic_id": row.get("id"),
                "title": row.get("title"),
                "summary": row.get("summary"),
                "topic_kind": row.get("topic_kind"),
                "archived": row.get("archived"),
                "detail": detail,
                "fields": fields,
                "salience": row.get("salience"),
            }

        if name == "memory_get_topic":
            tid = str(args.get("topic_id") or "")
            if not tid:
                return {"ok": False, "error": "topic_id required"}
            row = s.get_topic(tid)
            if not row:
                return {"ok": False, "error": "topic not found"}
            tf = TopicFields.from_json(row.get("fields_json") if isinstance(row.get("fields_json"), str) else "")
            names = list(tf.fields.keys())
            self._bump_read_access_salience(tid, names)
            row = s.get_topic(tid)
            tf = TopicFields.from_json(row.get("fields_json") if isinstance(row.get("fields_json"), str) else "")
            out_fields: dict[str, Any] = {}
            for fname, rec in tf.fields.items():
                out_fields[fname] = _field_to_topic_out(rec)
            return {
                "ok": True,
                "topic": {
                    "id": row.get("id"),
                    "title": row.get("title"),
                    "summary": row.get("summary"),
                    "topic_kind": row.get("topic_kind"),
                    "salience": row.get("salience"),
                    "failed_salience": row.get("failed_salience"),
                    "archived": row.get("archived"),
                    "fields": out_fields,
                    "created_at": row.get("created_at"),
                    "updated_at": row.get("updated_at"),
                },
            }

        if name == "memory_create_topic":
            title = str(args.get("title") or "untitled")
            tid = str(args.get("topic_id") or "") or str(uuid.uuid4())
            s.create_topic(
                tid,
                title=title,
                summary=args.get("summary"),
                salience=float(args.get("salience") or 1.0),
                archived=False,
                embedding=None,
                topic_kind=args.get("topic_kind"),
            )
            return {"ok": True, "topic_id": tid}

        if name == "memory_update_topic":
            tid = str(args.get("topic_id") or "")
            if not tid or not s.topic_exists(tid):
                return {"ok": False, "error": "topic not found"}
            kw: dict[str, Any] = {}
            if "title" in args:
                kw["title"] = args["title"]
            if "summary" in args:
                kw["summary"] = args["summary"]
            if "topic_kind" in args:
                kw["topic_kind"] = args["topic_kind"]
            if "salience" in args and args["salience"] is not None:
                kw["salience"] = float(args["salience"])
            if "archived" in args and args["archived"] is not None:
                kw["archived"] = bool(args["archived"])
            s.update_topic_meta(tid, **kw)
            return {"ok": True, "topic_id": tid}

        if name == "memory_delete_topic":
            tid = str(args.get("topic_id") or "")
            if not tid or not s.topic_exists(tid):
                return {"ok": False, "error": "topic not found"}
            s.delete_topic(tid)
            return {"ok": True, "deleted": tid}

        if name == "memory_add_relationship":
            a = str(args.get("from_topic_id") or "")
            b = str(args.get("to_topic_id") or "")
            k = str(args.get("kind") or "")
            if not s.topic_exists(a) or not s.topic_exists(b):
                return {"ok": False, "error": "topic not found"}
            s.add_relationship(a, b, k)
            return {"ok": True}

        if name == "memory_remove_relationship":
            a = str(args.get("from_topic_id") or "")
            b = str(args.get("to_topic_id") or "")
            k = str(args.get("kind") or "")
            s.remove_relationship(a, b, k)
            return {"ok": True}

        if name == "memory_append_field":
            tid = str(args.get("topic_id") or "")
            fname = str(args.get("field_name") or "")
            if not tid or not fname:
                return {"ok": False, "error": "topic_id and field_name required"}
            if not s.topic_exists(tid):
                return {"ok": False, "error": "topic not found"}
            entry = new_history_entry(
                value=args.get("value", ""),
                valid_from=_utc_iso(),
                provenance=str(args.get("provenance") or "llm"),
                why_changed=args.get("why_changed"),
            )
            if "ref_topic_id" not in args:
                ref_kw = REF_UNCHANGED
            else:
                r = args.get("ref_topic_id")
                ref_kw = None if r in (None, "") else str(r)
            vid = s.append_field_history(
                tid,
                fname,
                entry,
                field_type=str(args.get("field_type") or "string"),
                ref_topic_id=ref_kw,
            )
            return {"ok": True, "version_id": vid}

        if name == "memory_get_field":
            tid = str(args.get("topic_id") or "")
            fname = str(args.get("field_name") or "")
            tf = s.get_field_with_history(tid, fname)
            if not tf:
                return {"ok": False, "error": "field not found"}
            self._bump_read_access_salience(tid, [fname])
            tf2 = s.get_field_with_history(tid, fname)
            if not tf2:
                return {"ok": False, "error": "field not found"}
            return {
                "ok": True,
                "field": {
                    "field_type": tf2.field_type,
                    "ref_topic_id": tf2.ref_topic_id,
                    "salience": tf2.salience,
                    "history": [e.model_dump() for e in tf2.history],
                },
            }

        if name == "memory_delete_field":
            tid = str(args.get("topic_id") or "")
            fname = str(args.get("field_name") or "")
            s.delete_field(tid, fname)
            return {"ok": True, "deleted": fname}

        if name == "memory_set_field_ref":
            tid = str(args.get("topic_id") or "")
            fname = str(args.get("field_name") or "")
            ref = args.get("ref_topic_id")
            ref_s = None if ref in (None, "") else str(ref)
            s.set_field_ref(tid, fname, ref_s)
            return {"ok": True}

        if name in _REORGANIZE_TOOL_TO_OP:
            op = _REORGANIZE_TOOL_TO_OP[name]
            criteria = str(args.get("criteria") or "").strip()
            snap = _topics_schema_snapshot(s)
            topics = snap.get("topics") if isinstance(snap.get("topics"), list) else []
            edges = snap.get("edges") if isinstance(snap.get("edges"), list) else []
            return {
                "ok": True,
                "tool": name,
                "operation": op,
                "criteria": criteria,
                "guidelines": _REORGANIZE_GUIDELINES[op],
                "metrics": {
                    "topic_count": len(topics),
                    "related_edge_count": len(edges),
                },
                "topics_schema_snapshot": snap,
            }

        return {"ok": False, "error": f"unknown tool: {name}"}
