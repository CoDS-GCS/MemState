"""Map memory tool calls to graph visualization hints for the agent UI."""

from __future__ import annotations

import json
from typing import Any, Literal

from memstate.datamodel.fields import is_nested_fields_bundle_value, nested_bundle_inner_fields

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
        "memory_get_field_history",
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


def _field_value_from_result_field(field: dict[str, Any]) -> Any:
    hist = field.get("history")
    if isinstance(hist, list) and hist:
        first = hist[0]
        if isinstance(first, dict):
            return first.get("value")
    return field.get("value")


def _field_result_is_nested_bundle(result: dict[str, Any] | None) -> bool:
    if not result or not isinstance(result, dict):
        return False
    field = result.get("field")
    if not isinstance(field, dict):
        return False
    return is_nested_fields_bundle_value(_field_value_from_result_field(field))


def _inner_field_names_from_nested_bundle_result(result: dict[str, Any] | None) -> list[str]:
    if not result or not isinstance(result, dict):
        return []
    field = result.get("field")
    if not isinstance(field, dict):
        return []
    val = _field_value_from_result_field(field)
    inner = nested_bundle_inner_fields(val)
    return sorted(str(k) for k in inner.keys())


def _resolve_memory_get_field_viz(
    parsed_args: dict[str, Any],
    result: dict[str, Any] | None,
) -> tuple[dict[str, str] | None, list[str], str | None, bool]:
    """
    memory_get_field visualization.

    - nested_field_name / auto-resolved inner: one field under nest_key.
    - nest bundle read (field_name = personal_life, etc.): all inner field names.
    - top-level scalar: single field.
    """
    outer = _str_id(parsed_args.get("field_name"))
    nested_arg = _str_id(parsed_args.get("nested_field_name"))

    if result and isinstance(result, dict):
        rn = _str_id(result.get("nested_field_name"))
        if rn:
            rk = _str_id(result.get("nest_key")) or outer or ""
            ft = {"name": rn, "nest_key": rk}
            return ft, [rn], rk or None, True
        if outer and result.get("ok") is not False and _field_result_is_nested_bundle(result):
            inner = _inner_field_names_from_nested_bundle_result(result)
            if inner:
                return None, inner, outer, True
            return None, [], outer, False
        if outer and result.get("ok") is not False:
            return {"name": outer, "nest_key": ""}, [outer], None, True

    if nested_arg and outer:
        return {"name": nested_arg, "nest_key": outer}, [nested_arg], outer, True
    if outer:
        return {"name": outer, "nest_key": ""}, [outer], None, True
    return None, [], None, False


def _field_target_from_get_field(
    parsed_args: dict[str, Any],
    result: dict[str, Any] | None,
) -> dict[str, str] | None:
    """Single primary field target (legacy); use _resolve_memory_get_field_viz for bundles."""
    ft, _names, _nk, _hi = _resolve_memory_get_field_viz(parsed_args, result)
    return ft


def _field_target_for_tool(
    tool: str,
    parsed_args: dict[str, Any],
    result: dict[str, Any] | None,
) -> dict[str, str] | None:
    if tool in ("memory_get_field", "memory_get_field_history"):
        return _field_target_from_get_field(parsed_args, result)
    if tool in _WRITE_FIELD_TOOLS:
        fn = _str_id(parsed_args.get("field_name"))
        if fn:
            return {"name": fn, "nest_key": ""}
    return None


def _viz_focus_for_tool(
    tool: str,
    action: VizAction,
    field_target: dict[str, str] | None,
    *,
    field_names: list[str] | None = None,
) -> Literal["scan", "topic", "field"]:
    names = field_names or []
    if action == "scan":
        return "scan"
    if tool in ("memory_get_topic_schema", "memory_get_topic"):
        return "topic"
    if tool in ("memory_get_field", "memory_get_field_history"):
        return "field" if names or field_target else "topic"
    if tool in _WRITE_FIELD_TOOLS and field_target:
        return "field"
    if action == "write_edge":
        return "topic"
    if field_target:
        return "field"
    return "topic"


def _field_names_from_result(tool: str, args: dict[str, Any], result: dict[str, Any]) -> list[str]:
    """
    Field-level viz targets from tool results.

    - memory_get_field: args only (single field).
    - memory_get_topic_schema: only when detail is current/history (fields with values loaded).
    - memory_get_topic: topic-level only (no field list from result).
    """
    if tool in ("memory_get_field", "memory_get_field_history"):
        return []

    # Schema / full-topic reads are topic-level in the UI; field values use memory_get_field.
    if tool in ("memory_get_topic_schema", "memory_get_topic"):
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
        if tool == "memory_get_topic_schema":
            detail = str(args.get("detail") or "minimal").strip().lower()
            if topic_hint:
                return f"Reading topic schema ({detail}) — {topic_hint}"
            return f"Reading topic schema ({detail})"
        if tool in ("memory_get_field", "memory_get_field_history"):
            nested_fn = _str_id(args.get("nested_field_name"))
            outer_fn = _str_id(args.get("field_name"))
            if nested_fn and outer_fn:
                return f"Reading field {nested_fn} (in {outer_fn})"
            if outer_fn and result and _field_result_is_nested_bundle(result):
                inner = _inner_field_names_from_nested_bundle_result(result)
                if inner:
                    return f"Reading {len(inner)} fields in {outer_fn}"
            if outer_fn:
                label = "Reading field history" if tool == "memory_get_field_history" else "Reading field"
                return f"{label} {outer_fn}"
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

    field_target: dict[str, str] | None = None
    field_names: list[str] = []
    nest_key: str | None = None
    highlight_fields = False
    viz_focus: Literal["scan", "topic", "field"] = "topic"

    if tool in ("memory_get_field", "memory_get_field_history"):
        field_target, field_names, nest_key, highlight_fields = _resolve_memory_get_field_viz(
            parsed_args,
            result if isinstance(result, dict) else None,
        )
        viz_focus = _viz_focus_for_tool(tool, action, field_target, field_names=field_names)
    else:
        field_target = _field_target_for_tool(
            tool,
            parsed_args,
            result if isinstance(result, dict) else None,
        )
        if field_target:
            field_names = [field_target["name"]]
            nk = field_target.get("nest_key") or ""
            nest_key = nk or None
        viz_focus = _viz_focus_for_tool(tool, action, field_target, field_names=field_names)
        highlight_fields = viz_focus == "field"

    if tool not in ("memory_get_field", "memory_get_field_history", *tuple(_WRITE_FIELD_TOOLS)):
        if result and isinstance(result, dict):
            for tid in _topic_ids_from_result(result):
                if tid not in topic_ids:
                    topic_ids.append(tid)
            for fname in _field_names_from_result(tool, parsed_args, result):
                if fname not in field_names:
                    field_names.append(fname)
            if field_names and not field_target:
                field_target = {"name": field_names[0], "nest_key": ""}
                if len(field_names) > 1:
                    field_target = {"name": field_names[0], "nest_key": ""}

        if tool in ("memory_get_topic_schema", "memory_get_topic"):
            field_names = []
            field_target = None
            nest_key = None
            highlight_fields = False
            viz_focus = "topic"

    if result and isinstance(result, dict):
        for tid in _topic_ids_from_result(result):
            if tid not in topic_ids:
                topic_ids.append(tid)

    edge: dict[str, str] | None = None
    if action == "write_edge":
        a = _str_id(parsed_args.get("from_topic_id"))
        b = _str_id(parsed_args.get("to_topic_id"))
        k = _str_id(parsed_args.get("kind")) or "RELATED"
        if a and b:
            edge = {"from_topic_id": a, "to_topic_id": b, "kind": k}

    field_target_out: dict[str, str] | None = None
    if field_target:
        field_target_out = {"name": field_target["name"]}
        nk = (field_target.get("nest_key") or "").strip()
        if nk:
            field_target_out["nest_key"] = nk

    res_ok = result is None or (isinstance(result, dict) and result.get("ok") is not False)

    return {
        "action": action,
        "viz_focus": viz_focus,
        "topic_ids": topic_ids,
        "field_target": field_target_out,
        "field_names": field_names,
        "nest_key": nest_key,
        "highlight_fields": highlight_fields,
        "edge": edge,
        "label": _label_for(action, tool, parsed_args, result if isinstance(result, dict) else None),
        "ok": res_ok,
    }
