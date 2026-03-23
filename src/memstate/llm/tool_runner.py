"""Execute memory tool calls against GraphStore (shared by HTTP chat and MCP)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from memstate.api.ui_graph_payload import build_ui_graph_snapshot
from memstate.datamodel.fields import TopicFields, new_history_entry
from memstate.store.graph_store import REF_UNCHANGED, GraphStore


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _graph_snapshot(store: GraphStore) -> dict[str, Any]:
    """Same shape as GET /api/ui/graph (includes ``community`` per node)."""
    return build_ui_graph_snapshot(store)


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
            }
        elif d == "current":
            cur = rec.current_entry()
            out[fname] = {
                "field_type": rec.field_type,
                "ref_topic_id": rec.ref_topic_id,
                "value": cur.value if cur else None,
            }
        else:
            out[fname] = {
                "field_type": rec.field_type,
                "ref_topic_id": rec.ref_topic_id,
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


class MemoryToolRunner:
    def __init__(self, store: GraphStore) -> None:
        self._store = store

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
            }

        if name == "memory_get_topic":
            tid = str(args.get("topic_id") or "")
            if not tid:
                return {"ok": False, "error": "topic_id required"}
            row = s.get_topic(tid)
            if not row:
                return {"ok": False, "error": "topic not found"}
            tf = TopicFields.from_json(row.get("fields_json") if isinstance(row.get("fields_json"), str) else "")
            out_fields: dict[str, Any] = {}
            for fname, rec in tf.fields.items():
                out_fields[fname] = {
                    "field_type": rec.field_type,
                    "ref_topic_id": rec.ref_topic_id,
                    "history": [e.model_dump() for e in rec.history],
                }
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
            return {
                "ok": True,
                "field": {
                    "field_type": tf.field_type,
                    "ref_topic_id": tf.ref_topic_id,
                    "history": [e.model_dump() for e in tf.history],
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

        return {"ok": False, "error": f"unknown tool: {name}"}
