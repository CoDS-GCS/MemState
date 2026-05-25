"""Execute memory tool calls against GraphStore (shared by HTTP chat and MCP)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from memstate.api.ui_graph_payload import (
    build_study_graph_snapshot,
    build_topics_schema_snapshot,
    build_ui_graph_snapshot,
)
from memstate.datamodel.fields import (
    TopicField,
    TopicFields,
    is_nested_fields_bundle_value,
    nested_bundle_inner_fields,
    new_history_entry,
)
from memstate.llm.tools_schema import IntentRoute
from memstate.store.graph_store import REF_UNCHANGED, GraphStore


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _field_payload_from_topic_field(tf: TopicField, *, with_history: bool = True) -> dict[str, Any]:
    cur = tf.current_entry()
    payload: dict[str, Any] = {
        "field_type": tf.field_type,
        "ref_topic_id": tf.ref_topic_id,
        "salience": tf.salience,
        "value": cur.value if cur else None,
    }
    if with_history:
        payload["history"] = [e.model_dump() for e in tf.history]
        payload["history_count"] = len(tf.history)
    return payload


def _read_nested_inner_field(
    nest_key: str,
    inner_name: str,
    inner_raw: dict[str, Any],
    *,
    with_history: bool = True,
) -> dict[str, Any]:
    sub_tf = TopicField.model_validate(inner_raw)
    return {
        "ok": True,
        "nest_key": nest_key,
        "nested_field_name": inner_name,
        "field": _field_payload_from_topic_field(sub_tf, with_history=with_history),
    }


def _find_nested_inner_field(store: GraphStore, topic_id: str, inner_name: str) -> tuple[str, dict[str, Any]] | None:
    """Return (nest_key, inner TopicField dict) when inner_name lives in a nest bundle."""
    for nest_key in store.list_field_names(topic_id):
        rec = store.get_field_with_history(topic_id, nest_key)
        if not rec:
            continue
        cur = rec.current_entry()
        if not cur or not is_nested_fields_bundle_value(cur.value):
            continue
        inner = nested_bundle_inner_fields(cur.value)
        sub_raw = inner.get(inner_name)
        if isinstance(sub_raw, dict):
            return nest_key, sub_raw
    return None


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
        "kinds. Plan **separate** topics when subjects are unrelated. This is **not** in-topic nesting: for grouping "
        "related fields **inside one topic** (json bundle, no new node), use memory_nest_fields_in_topic."
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

# Parent→child nesting for Study (at most one level: section parent cannot be a child).
_STUDY_PARENT_CHILD_KINDS = frozenset({"study_child", "part_of"})


def _topic_has_incoming_parent_child(store: GraphStore, topic_id: str) -> bool:
    for r in store.list_relationships(topic_id, direction="in"):
        if str(r.get("kind") or "") in _STUDY_PARENT_CHILD_KINDS:
            return True
    return False


_REORGANIZE_TOOL_TO_OP: dict[str, str] = {
    "memory_reorganize_consolidation": "consolidation",
    "memory_reorganize_merge_topics": "merge_topics",
    "memory_reorganize_split_topics": "split_topics",
    "memory_reorganize_connect_topics": "connect_topics",
    "memory_reorganize_retention_trim": "retention_trim",
}


def _nested_bundle_schema_extras(rec: TopicField, *, with_current_values: bool) -> dict[str, Any]:
    cur = rec.current_entry()
    if rec.field_type != "json" or not cur or not is_nested_fields_bundle_value(cur.value):
        return {}
    inner = nested_bundle_inner_fields(cur.value)
    names = sorted(inner.keys())
    out: dict[str, Any] = {"nested_field_names": names}
    if not with_current_values:
        return out
    subvals: dict[str, Any] = {}
    for n in names:
        sub = inner.get(n)
        if isinstance(sub, dict):
            try:
                stf = TopicField.model_validate(sub)
                sce = stf.current_entry()
                subvals[n] = sce.value if sce else None
            except Exception:
                subvals[n] = None
        else:
            subvals[n] = None
    out["nested_fields_current"] = subvals
    return out


def _fields_schema_payload(tf: TopicFields, *, detail: str) -> dict[str, Any]:
    """Build per-field payload for memory_get_topic_schema (detail: minimal | current | history)."""
    out: dict[str, Any] = {}
    d = (detail or "minimal").strip().lower()
    if d not in ("minimal", "current", "history"):
        d = "minimal"
    for fname, rec in tf.fields.items():
        if d == "minimal":
            row = {
                "field_type": rec.field_type,
                "ref_topic_id": rec.ref_topic_id,
                "salience": rec.salience,
            }
            row.update(_nested_bundle_schema_extras(rec, with_current_values=False))
            out[fname] = row
        elif d == "current":
            cur = rec.current_entry()
            row = {
                "field_type": rec.field_type,
                "ref_topic_id": rec.ref_topic_id,
                "salience": rec.salience,
                "value": cur.value if cur else None,
            }
            row.update(_nested_bundle_schema_extras(rec, with_current_values=True))
            out[fname] = row
        else:
            row = {
                "field_type": rec.field_type,
                "ref_topic_id": rec.ref_topic_id,
                "salience": rec.salience,
                "history": [e.model_dump() for e in rec.history],
            }
            row.update(_nested_bundle_schema_extras(rec, with_current_values=False))
            out[fname] = row
    return out


def _topic_history_from_row(row: dict[str, Any]) -> list[Any]:
    raw = row.get("topic_history_json")
    if not isinstance(raw, str) or not raw.strip():
        return []
    try:
        v = json.loads(raw)
        return v if isinstance(v, list) else []
    except json.JSONDecodeError:
        return []


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
    return _field_payload_from_topic_field(rec, with_history=True)


def _parse_with_history_flag(raw: Any, *, default: bool = True) -> bool:
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        s = raw.strip().lower()
        if s in ("false", "0", "no", "off"):
            return False
        if s in ("true", "1", "yes", "on"):
            return True
    return default


class MemoryToolRunner:
    def __init__(
        self,
        store: GraphStore,
        *,
        chat_route: IntentRoute | None = None,
        query_field_salience_bump: float = 0.1,
        field_salience_max: float = 10.0,
        study_session_kind: str | None = None,
        study_catalog: dict[str, Any] | None = None,
    ) -> None:
        self._store = store
        self._chat_route = chat_route
        self._query_bump = query_field_salience_bump
        self._field_salience_max = field_salience_max
        self._study_kind = (study_session_kind or "").strip() or None
        self._study_catalog = study_catalog

    def _study_topic_kind_ok(self, topic_id: str) -> bool:
        if not self._study_kind:
            return True
        row = self._store.get_topic(topic_id)
        if not row:
            return False
        return str(row.get("topic_kind") or "") == self._study_kind

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

    def _get_field_result(self, args: dict[str, Any], *, with_history: bool) -> dict[str, Any]:
        s = self._store
        tid = str(args.get("topic_id") or "").strip()
        fname = str(args.get("field_name") or "").strip()
        nested_fname = str(args.get("nested_field_name") or "").strip()
        if not tid or not fname:
            return {"ok": False, "error": "topic_id and field_name required"}
        if self._study_kind and not self._study_topic_kind_ok(tid):
            return {"ok": False, "error": "topic not in this Study session"}

        if nested_fname:
            tf = s.get_field_with_history(tid, fname)
            if not tf:
                return {"ok": False, "error": "field not found"}
            cur = tf.current_entry()
            if not cur or not is_nested_fields_bundle_value(cur.value):
                return {"ok": False, "error": "field is not a nested bundle"}
            inner = nested_bundle_inner_fields(cur.value)
            sub_raw = inner.get(nested_fname)
            if not isinstance(sub_raw, dict):
                return {"ok": False, "error": "nested field not found"}
            try:
                self._bump_read_access_salience(tid, [fname])
                return _read_nested_inner_field(
                    fname, nested_fname, sub_raw, with_history=with_history
                )
            except Exception:
                return {"ok": False, "error": "nested field invalid"}

        tf = s.get_field_with_history(tid, fname)
        if tf:
            self._bump_read_access_salience(tid, [fname])
            return {
                "ok": True,
                "topic_id": tid,
                "field_name": fname,
                "field": _field_payload_from_topic_field(tf, with_history=with_history),
            }

        found = _find_nested_inner_field(s, tid, fname)
        if found:
            nest_key, sub_raw = found
            try:
                self._bump_read_access_salience(tid, [nest_key])
                out = _read_nested_inner_field(
                    nest_key, fname, sub_raw, with_history=with_history
                )
                out["topic_id"] = tid
                out["field_name"] = fname
                return out
            except Exception:
                return {"ok": False, "error": "nested field invalid"}

        return {"ok": False, "error": "field not found"}

    def execute(self, name: str, arguments: Any) -> dict[str, Any]:
        args = _parse_args(arguments)
        try:
            return self._dispatch(name, args)
        except Exception as e:
            return {"ok": False, "error": str(e), "tool": name}

    def _dispatch(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        s = self._store

        if name == "memory_graph_snapshot":
            if self._study_kind:
                return {
                    "ok": False,
                    "error": "In Study phase A use study_graph_snapshot, not memory_graph_snapshot.",
                }
            return {"ok": True, "data": _graph_snapshot(s)}

        if name == "memory_list_topics":
            inc = bool(args.get("include_archived", False))
            topics = s.list_topics_meta(
                include_archived=inc,
                topic_kind=self._study_kind,
            )
            return {
                "ok": True,
                "topics": topics,
                "topic_ids": [t["id"] for t in topics],
            }

        if name == "memory_topics_schema_page":
            off = int(args.get("offset") or 0)
            lim = int(args.get("limit") or 15)
            inc = bool(args.get("include_archived", False))
            tk_arg = args.get("topic_kind")
            tk_use: str | None
            if self._study_kind:
                tk_use = self._study_kind
            elif tk_arg is not None and str(tk_arg).strip() != "":
                tk_use = str(tk_arg).strip()
            else:
                tk_use = None
            from memstate.api.ui_graph_payload import build_topics_schema_page

            page = build_topics_schema_page(
                s,
                offset=off,
                limit=lim,
                include_archived=inc,
                topic_kind=tk_use,
            )
            return {"ok": True, **page}

        if name == "memory_get_topic_schema":
            tid = str(args.get("topic_id") or "")
            if not tid:
                return {"ok": False, "error": "topic_id required"}
            if self._study_kind and not self._study_topic_kind_ok(tid):
                return {"ok": False, "error": "topic not in this Study session"}
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
            if self._study_kind and not self._study_topic_kind_ok(tid):
                return {"ok": False, "error": "topic not in this Study session"}
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
                    "topic_history": _topic_history_from_row(row),
                    "created_at": row.get("created_at"),
                    "updated_at": row.get("updated_at"),
                },
            }

        if name == "memory_create_topic":
            title = str(args.get("title") or "untitled")
            tid = str(args.get("topic_id") or "") or str(uuid.uuid4())
            tk = args.get("topic_kind")
            if self._study_kind:
                tk = self._study_kind
            s.create_topic(
                tid,
                title=title,
                summary=args.get("summary"),
                salience=float(args.get("salience") or 1.0),
                archived=False,
                embedding=None,
                topic_kind=tk,
            )
            return {"ok": True, "topic_id": tid}

        if name == "memory_update_topic":
            tid = str(args.get("topic_id") or "")
            if not tid or not s.topic_exists(tid):
                return {"ok": False, "error": "topic not found"}
            if self._study_kind and not self._study_topic_kind_ok(tid):
                return {"ok": False, "error": "topic not in this Study session"}
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
            if self._study_kind:
                kw["topic_kind"] = self._study_kind
            s.update_topic_meta(tid, **kw)
            return {"ok": True, "topic_id": tid}

        if name == "memory_delete_topic":
            tid = str(args.get("topic_id") or "")
            if not tid or not s.topic_exists(tid):
                return {"ok": False, "error": "topic not found"}
            if self._study_kind and not self._study_topic_kind_ok(tid):
                return {"ok": False, "error": "topic not in this Study session"}
            s.delete_topic(tid)
            return {"ok": True, "deleted": tid}

        if name == "memory_add_relationship":
            a = str(args.get("from_topic_id") or "")
            b = str(args.get("to_topic_id") or "")
            k = str(args.get("kind") or "")
            if not s.topic_exists(a) or not s.topic_exists(b):
                return {"ok": False, "error": "topic not found"}
            if self._study_kind:
                if not self._study_topic_kind_ok(a) or not self._study_topic_kind_ok(b):
                    return {
                        "ok": False,
                        "error": "Study phase A: only link topics in this session (same topic_kind).",
                    }
                if k in _STUDY_PARENT_CHILD_KINDS and _topic_has_incoming_parent_child(s, a):
                    return {
                        "ok": False,
                        "error": (
                            "Nesting limit: from_topic cannot be a detail topic (it already has an incoming "
                            f"{sorted(_STUDY_PARENT_CHILD_KINDS)} edge). Use at most one parent→child level."
                        ),
                    }
            s.add_relationship(a, b, k)
            return {"ok": True}

        if name == "memory_remove_relationship":
            a = str(args.get("from_topic_id") or "")
            b = str(args.get("to_topic_id") or "")
            k = str(args.get("kind") or "")
            if not s.topic_exists(a) or not s.topic_exists(b):
                return {"ok": False, "error": "topic not found"}
            if self._study_kind and (
                not self._study_topic_kind_ok(a) or not self._study_topic_kind_ok(b)
            ):
                return {"ok": False, "error": "topic not in this Study session"}
            s.remove_relationship(a, b, k)
            return {"ok": True}

        if name == "memory_append_field":
            tid = str(args.get("topic_id") or "")
            fname = str(args.get("field_name") or "")
            if not tid or not fname:
                return {"ok": False, "error": "topic_id and field_name required"}
            if "value" not in args:
                return {
                    "ok": False,
                    "error": "memory_append_field requires `value` with the fact to store. Omitting it used to record an empty string while still returning ok—retry with value set (use \"\" only if you intentionally mean an empty string).",
                }
            if not s.topic_exists(tid):
                return {"ok": False, "error": "topic not found"}
            if self._study_kind and not self._study_topic_kind_ok(tid):
                return {"ok": False, "error": "topic not in this Study session"}
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
            if (
                self._study_kind
                and ref_kw is not REF_UNCHANGED
                and ref_kw not in (None, "")
                and isinstance(ref_kw, str)
                and not self._study_topic_kind_ok(ref_kw)
            ):
                return {"ok": False, "error": "ref_topic_id must be a topic in this Study session"}
            vid = s.append_field_history(
                tid,
                fname,
                entry,
                field_type=str(args.get("field_type") or "string"),
                ref_topic_id=ref_kw,
            )
            return {"ok": True, "version_id": vid}

        if name == "memory_get_field":
            with_history = _parse_with_history_flag(args.get("with_history"), default=True)
            return self._get_field_result(args, with_history=with_history)

        if name == "memory_get_field_history":
            return self._get_field_result(args, with_history=True)

        if name == "memory_delete_field":
            tid = str(args.get("topic_id") or "")
            fname = str(args.get("field_name") or "")
            if self._study_kind and not self._study_topic_kind_ok(tid):
                return {"ok": False, "error": "topic not in this Study session"}
            s.delete_field(tid, fname)
            return {"ok": True, "deleted": fname}

        if name == "memory_set_field_ref":
            tid = str(args.get("topic_id") or "")
            fname = str(args.get("field_name") or "")
            ref = args.get("ref_topic_id")
            ref_s = None if ref in (None, "") else str(ref)
            if self._study_kind:
                if not self._study_topic_kind_ok(tid):
                    return {"ok": False, "error": "topic not in this Study session"}
                if ref_s and not self._study_topic_kind_ok(ref_s):
                    return {"ok": False, "error": "ref_topic_id must be in this Study session"}
            s.set_field_ref(tid, fname, ref_s)
            return {"ok": True}

        if name == "memory_nest_fields_in_topic":
            tid = str(args.get("topic_id") or "").strip()
            nk = str(args.get("nest_key") or "").strip()
            if not tid:
                return {"ok": False, "error": "topic_id required"}
            if not nk:
                return {"ok": False, "error": "nest_key required"}
            if not s.topic_exists(tid):
                return {"ok": False, "error": "topic not found"}
            if self._study_kind and not self._study_topic_kind_ok(tid):
                return {"ok": False, "error": "topic not in this Study session"}
            fr = args.get("field_names")
            if not isinstance(fr, list) or not fr:
                return {"ok": False, "error": "field_names must be a non-empty list of field name strings"}
            try:
                out = s.nest_fields_in_topic(
                    tid,
                    [str(x) for x in fr],
                    nk,
                    provenance=str(args.get("provenance") or "llm"),
                )
            except ValueError as e:
                return {"ok": False, "error": str(e)}
            return {"ok": True, **out}

        if name == "memory_unnest_fields_in_topic":
            tid = str(args.get("topic_id") or "").strip()
            nk = str(args.get("nest_key") or "").strip()
            if not tid or not nk:
                return {"ok": False, "error": "topic_id and nest_key required"}
            if not s.topic_exists(tid):
                return {"ok": False, "error": "topic not found"}
            if self._study_kind and not self._study_topic_kind_ok(tid):
                return {"ok": False, "error": "topic not in this Study session"}
            try:
                out = s.unnest_fields_in_topic(tid, nk)
            except ValueError as e:
                return {"ok": False, "error": str(e)}
            return {"ok": True, **out}

        if name == "memory_promote_fields_to_nested_topic":
            parent = str(args.get("parent_topic_id") or "").strip()
            if not parent:
                return {"ok": False, "error": "parent_topic_id required"}
            if not s.topic_exists(parent):
                return {"ok": False, "error": "parent topic not found"}
            if self._study_kind and not self._study_topic_kind_ok(parent):
                return {"ok": False, "error": "topic not in this Study session"}
            fr = args.get("field_names")
            if not isinstance(fr, list) or not fr:
                return {"ok": False, "error": "field_names must be a non-empty list of field name strings"}
            child_title = str(args.get("child_title") or "").strip()
            if not child_title:
                return {"ok": False, "error": "child_title required"}
            rk = str(args.get("relationship_kind") or "has_detail").strip() or "has_detail"
            if self._study_kind and rk in _STUDY_PARENT_CHILD_KINDS:
                if _topic_has_incoming_parent_child(s, parent):
                    return {
                        "ok": False,
                        "error": (
                            "Nesting limit: parent topic already has an incoming "
                            f"{sorted(_STUDY_PARENT_CHILD_KINDS)} edge. Use at most one parent→child level."
                        ),
                    }
            ctk = args.get("child_topic_kind")
            tk: str | None
            if self._study_kind:
                tk = self._study_kind
            elif ctk is not None and str(ctk).strip() != "":
                tk = str(ctk).strip()
            else:
                tk = None
            plf = args.get("parent_link_field")
            plf_s = None if plf in (None, "") else str(plf).strip()
            if plf_s == "":
                plf_s = None
            cid_raw = args.get("child_topic_id")
            cid = None if cid_raw in (None, "") else str(cid_raw).strip()
            try:
                out = s.promote_fields_to_nested_topic(
                    parent,
                    [str(x) for x in fr],
                    child_title,
                    child_summary=args.get("child_summary"),
                    child_topic_id=cid,
                    topic_kind=tk,
                    relationship_kind=rk,
                    parent_link_field=plf_s,
                    link_field_provenance=str(args.get("link_provenance") or "llm"),
                    max_history=int(args.get("max_history") or 500),
                )
            except ValueError as e:
                return {"ok": False, "error": str(e)}
            return {"ok": True, **out}

        if name == "memory_undo_promote_nested_topic":
            parent = str(args.get("parent_topic_id") or "").strip()
            child = str(args.get("child_topic_id") or "").strip()
            if not parent or not child:
                return {"ok": False, "error": "parent_topic_id and child_topic_id required"}
            if not s.topic_exists(parent) or not s.topic_exists(child):
                return {"ok": False, "error": "topic not found"}
            if self._study_kind and (
                not self._study_topic_kind_ok(parent) or not self._study_topic_kind_ok(child)
            ):
                return {"ok": False, "error": "topic not in this Study session"}
            rk = args.get("relationship_kind")
            rk_s = None if rk in (None, "") else str(rk).strip()
            try:
                out = s.undo_promote_nested_topic(parent, child, relationship_kind=rk_s)
            except ValueError as e:
                return {"ok": False, "error": str(e)}
            return {"ok": True, **out}

        if name == "study_unit_catalog":
            if not self._study_catalog:
                return {
                    "ok": True,
                    "catalog": {},
                    "note": "Empty catalog (use MemState Study chat or pass study_catalog on the runner).",
                }
            return {"ok": True, "catalog": self._study_catalog}

        if name == "study_graph_snapshot":
            if not self._study_kind:
                return {"ok": False, "error": "study_graph_snapshot is only available in Study phase A"}
            return {
                "ok": True,
                "data": build_study_graph_snapshot(s, self._study_kind),
            }

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
