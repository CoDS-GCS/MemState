"""Map memory tool calls to graph visualization hints for the agent UI."""

from __future__ import annotations

import json
from typing import Any, Literal

VizAction = Literal[
    "scan",
    "read",
    "write_field",
    "write_topic",
    "write_edge",
    "reorganize",
    "other",
]

_SCAN_TOOLS = frozenset(
    {
        "memory_list_topics",
        "memory_topics_schema_page",
        "memory_graph_snapshot",
        "study_graph_snapshot",
        "study_unit_catalog",
    }
)

_READ_TOOLS = frozenset(
    {
        "memory_get_topic_schema",
        "memory_get_topic",
        "memory_get_field",
    }
)

_WRITE_FIELD_TOOLS = frozenset(
    {
        "memory_append_field",
        "memory_delete_field",
        "memory_set_field_ref",
    }
)

_WRITE_TOPIC_TOOLS = frozenset(
    {
        "memory_create_topic",
        "memory_update_topic",
        "memory_delete_topic",
    }
)

_WRITE_EDGE_TOOLS = frozenset(
    {
        "memory_add_relationship",
        "memory_remove_relationship",
    }
)

_REORGANIZE_TOOLS = frozenset(
    {
        "memory_nest_fields_in_topic",
        "memory_unnest_fields_in_topic",
        "memory_promote_fields_to_nested_topic",
        "memory_undo_promote_nested_topic",
        "memory_reorganize_consolidation",
        "memory_reorganize_merge_topics",
        "memory_reorganize_split_topics",
        "memory_reorganize_connect_topics",
        "memory_reorganize_retention_trim",
    }
)


def _parse_args(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            v = json.loads(raw)
            return v if isinstance(v, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _str_id(val: Any) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    return s or None


def _topic_ids_from_result(result: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()

    def add(tid: str | None) -> None:
        if tid and tid not in seen:
            seen.add(tid)
            ids.append(tid)

    add(_str_id(result.get("topic_id")))
    add(_str_id(result.get("deleted")))
    if isinstance(result.get("topic_ids"), list):
        for x in result["topic_ids"]:
            add(_str_id(x))
    topic = result.get("topic")
    if isinstance(topic, dict):
        add(_str_id(topic.get("id")))
    topics = result.get("topics")
    if isinstance(topics, list):
        for t in topics:
            if isinstance(t, dict):
                add(_str_id(t.get("id")))
    data = result.get("data")
    if isinstance(data, dict):
        nodes = data.get("nodes")
        if isinstance(nodes, list):
            for n in nodes:
                if isinstance(n, dict):
                    add(_str_id(n.get("id")))
    snap = result.get("topics_schema_snapshot")
    if isinstance(snap, dict):
        topics2 = snap.get("topics")
        if isinstance(topics2, list):
            for t in topics2:
                if isinstance(t, dict):
                    add(_str_id(t.get("id")))
    page_topics = result.get("topics")
    if isinstance(page_topics, list) and "offset" in result:
        for t in page_topics:
            if isinstance(t, dict):
                add(_str_id(t.get("id")))
    child = result.get("child_topic_id")
    add(_str_id(child))
    return ids


def _topic_ids_from_args(args: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()

    def add(tid: str | None) -> None:
        if tid and tid not in seen:
            seen.add(tid)
            ids.append(tid)

    for key in (
        "topic_id",
        "from_topic_id",
        "to_topic_id",
        "parent_topic_id",
        "child_topic_id",
        "ref_topic_id",
    ):
        add(_str_id(args.get(key)))
    return ids


def _field_names_from_result(tool: str, args: dict[str, Any], result: dict[str, Any]) -> list[str]:
    """
    Field-level viz targets from tool results.

    - memory_get_field: args only (single field).
    - memory_get_topic_schema: only when detail is current/history (fields with values loaded).
    - memory_get_topic: topic-level only (no field list from result).
    """
    if tool == "memory_get_field":
        return []

    if tool == "memory_get_topic_schema":
        detail = str(args.get("detail") or "minimal").strip().lower()
        if detail not in ("current", "history"):
            return []
        fields = result.get("fields")
        if not isinstance(fields, dict):
            return []
        names: list[str] = []
        for key, payload in fields.items():
            name = _str_id(key)
            if not name or not isinstance(payload, dict):
                continue
            if detail == "history":
                hist = payload.get("history")
                if isinstance(hist, list) and hist:
                    names.append(name)
            elif "value" in payload:
                names.append(name)
        return names

    if tool == "memory_get_topic":
        return []

    names: list[str] = []
    seen: set[str] = set()

    def add(name: str | None) -> None:
        if name and name not in seen:
            seen.add(name)
            names.append(name)

    fields = result.get("fields")
    if isinstance(fields, dict):
        for key in fields.keys():
            add(_str_id(key))

    topic = result.get("topic")
    if isinstance(topic, dict):
        tf = topic.get("fields")
        if isinstance(tf, dict):
            for key in tf.keys():
                add(_str_id(key))

    return names


def _field_names_from_args(args: dict[str, Any]) -> list[str]:
    names: list[str] = []
    fn = _str_id(args.get("field_name"))
    if fn:
        names.append(fn)
    nest = args.get("nest_key")
    nk = _str_id(nest)
    if nk:
        names.append(nk)
    fr = args.get("field_names")
    if isinstance(fr, list):
        for x in fr:
            n = _str_id(x)
            if n and n not in names:
                names.append(n)
    plf = _str_id(args.get("parent_link_field"))
    if plf and plf not in names:
        names.append(plf)
    return names


def _action_for_tool(tool: str) -> VizAction:
    if tool in _SCAN_TOOLS:
        return "scan"
    if tool in _READ_TOOLS:
        return "read"
    if tool in _WRITE_FIELD_TOOLS:
        return "write_field"
    if tool in _WRITE_TOPIC_TOOLS:
        return "write_topic"
    if tool in _WRITE_EDGE_TOOLS:
        return "write_edge"
    if tool in _REORGANIZE_TOOLS:
        return "reorganize"
    return "other"


def _label_for(action: VizAction, tool: str, args: dict[str, Any], result: dict[str, Any] | None) -> str:
    tid = _topic_ids_from_args(args)
    fields = _field_names_from_args(args)
    topic_hint = tid[0][:8] + "…" if tid else ""
    field_hint = fields[0] if fields else ""

    if action == "scan":
        n = 0
        if result:
            if isinstance(result.get("topic_ids"), list):
                n = len(result["topic_ids"])
            elif isinstance(result.get("topics"), list):
                n = len(result["topics"])
            elif isinstance(result.get("data"), dict):
                nodes = result["data"].get("nodes")
                if isinstance(nodes, list):
                    n = len(nodes)
        if n:
            return f"Scanning {n} topics"
        return "Scanning topics"

    if action == "read":
        if tool == "memory_get_field" and field_hint:
            return f"Reading field {field_hint}"
        if field_hint:
            return f"Reading topic schema ({field_hint})"
        if topic_hint:
            return f"Reading topic {topic_hint}"
        return "Reading topic"

    if action == "write_field":
        if field_hint:
            return f"Writing field {field_hint}"
        return "Writing field"

    if action == "write_topic":
        if tool == "memory_create_topic":
            title = _str_id(args.get("title"))
            return f"Creating topic {title or '…'}"
        if tool == "memory_delete_topic":
            return f"Deleting topic {topic_hint or '…'}"
        return f"Updating topic {topic_hint or '…'}"

    if action == "write_edge":
        kind = _str_id(args.get("kind")) or "RELATED"
        return f"Linking topics ({kind})"

    if action == "reorganize":
        return f"Reorganizing memory ({tool.replace('memory_', '')})"

    return tool.replace("memory_", "").replace("_", " ")


def build_viz_hint(
    tool: str,
    args: Any,
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build visualization hint for a memory tool call.

    Returns dict with action, topic_ids, field_names, edge (optional), label.
    """
    parsed_args = _parse_args(args)
    action = _action_for_tool(tool)
    topic_ids = _topic_ids_from_args(parsed_args)
    field_names = _field_names_from_args(parsed_args)

    if result and isinstance(result, dict):
        for tid in _topic_ids_from_result(result):
            if tid not in topic_ids:
                topic_ids.append(tid)
        for fname in _field_names_from_result(tool, parsed_args, result):
            if fname not in field_names:
                field_names.append(fname)

    # Single-field tools must always expose the target field when arg is set.
    if tool in ("memory_get_field", *tuple(_WRITE_FIELD_TOOLS)):
        fn = _str_id(parsed_args.get("field_name"))
        if fn and fn not in field_names:
            field_names.append(fn)

    edge: dict[str, str] | None = None
    if action == "write_edge":
        a = _str_id(parsed_args.get("from_topic_id"))
        b = _str_id(parsed_args.get("to_topic_id"))
        k = _str_id(parsed_args.get("kind")) or "RELATED"
        if a and b:
            edge = {"from_topic_id": a, "to_topic_id": b, "kind": k}

    res_ok = result is None or (isinstance(result, dict) and result.get("ok") is not False)

    return {
        "action": action,
        "topic_ids": topic_ids,
        "field_names": field_names,
        "highlight_fields": len(field_names) > 0,
        "edge": edge,
        "label": _label_for(action, tool, parsed_args, result if isinstance(result, dict) else None),
        "ok": res_ok,
    }
