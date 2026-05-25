"""MCP stdio server exposing the same memory tools as the UI chat (for Claude Desktop, etc.)."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from memstate.llm.tool_runner import MemoryToolRunner
from memstate.llm.tools_schema import TOPIC_VS_ENTITY_PROMPT
from memstate.store.graph_store import get_store

mcp = FastMCP(
    "memstate-memory",
    instructions=(
        "MemState topic graph memory: use these tools to read and edit topics, fields, "
        "and RELATED relationships. Call memory_graph_snapshot for the full graph with values. "
        "memory_topics_schema_page returns paginated schema-only slices (no values)—use offset/next_offset to scan all topics. "
        "Study long-document ingest (HTTP API) uses two phases: phase A sandbox (topic_kind study:<uuid>) "
        "then phase B integration. For MCP, use study_graph_snapshot(study_topic_kind) to view a session subgraph; "
        "study_unit_catalog is populated only when the runner carries a catalog (HTTP Study chat). "
        "For reorganization, use memory_reorganize_consolidation, memory_reorganize_merge_topics, "
        "memory_reorganize_split_topics, memory_reorganize_connect_topics, or "
        "memory_reorganize_retention_trim—each returns topics_schema_snapshot (structure only). "
        "memory_nest_fields_in_topic groups fields inside the same topic (json bundle, no new graph node); "
        "memory_unnest_fields_in_topic expands the bundle. "
        "memory_promote_fields_to_nested_topic is rare—it creates a separate child Topic (advanced). "
        "For merge_topics, compare current values (get_topic_schema current) for overlap before merging. "
        "Use memory_get_topic_schema / memory_get_topic when values are needed before writes.\n\n"
        + TOPIC_VS_ENTITY_PROMPT
    ),
)


def _runner() -> MemoryToolRunner:
    return MemoryToolRunner(get_store())


@mcp.tool()
def memory_graph_snapshot() -> dict[str, Any]:
    """Return all topics and edges for visualization and discovery."""
    return _runner().execute("memory_graph_snapshot", {})


@mcp.tool()
def memory_list_topics(include_archived: bool = False) -> dict[str, Any]:
    """List topics with id, title, summary, topic_kind, and archived (not ids only)."""
    return _runner().execute("memory_list_topics", {"include_archived": include_archived})


@mcp.tool()
def memory_topics_schema_page(
    offset: int = 0,
    limit: int = 15,
    include_archived: bool = False,
    topic_kind: str = "",
) -> dict[str, Any]:
    """Paginated schema-only topics (no values/history). Iterate offset until has_more is false."""
    args: dict[str, Any] = {
        "offset": offset,
        "limit": limit,
        "include_archived": include_archived,
    }
    if topic_kind.strip():
        args["topic_kind"] = topic_kind.strip()
    return _runner().execute("memory_topics_schema_page", args)


@mcp.tool()
def memory_get_topic_schema(
    topic_id: str,
    detail: str = "minimal",
) -> dict[str, Any]:
    """Field schema for one topic: minimal (names/types), current (+ latest value), or history (full)."""
    return _runner().execute(
        "memory_get_topic_schema",
        {"topic_id": topic_id, "detail": detail},
    )


@mcp.tool()
def memory_get_topic(topic_id: str) -> dict[str, Any]:
    """Load full topic record including fields and history."""
    return _runner().execute("memory_get_topic", {"topic_id": topic_id})


@mcp.tool()
def memory_create_topic(
    title: str,
    summary: str | None = None,
    topic_kind: str | None = None,
    salience: float = 1.0,
    topic_id: str | None = None,
) -> dict[str, Any]:
    """Create a new topic only after memory_list_topics confirms the subject is not already stored; otherwise update the existing topic."""
    args: dict[str, Any] = {"title": title, "salience": salience}
    if summary is not None:
        args["summary"] = summary
    if topic_kind is not None:
        args["topic_kind"] = topic_kind
    if topic_id is not None:
        args["topic_id"] = topic_id
    return _runner().execute("memory_create_topic", args)


@mcp.tool()
def memory_update_topic(
    topic_id: str,
    title: str | None = None,
    summary: str | None = None,
    topic_kind: str | None = None,
    salience: float | None = None,
    archived: bool | None = None,
) -> dict[str, Any]:
    """Update topic metadata (only pass fields to change)."""
    args: dict[str, Any] = {"topic_id": topic_id}
    if title is not None:
        args["title"] = title
    if summary is not None:
        args["summary"] = summary
    if topic_kind is not None:
        args["topic_kind"] = topic_kind
    if salience is not None:
        args["salience"] = salience
    if archived is not None:
        args["archived"] = archived
    return _runner().execute("memory_update_topic", args)


@mcp.tool()
def memory_delete_topic(topic_id: str) -> dict[str, Any]:
    """Delete a topic."""
    return _runner().execute("memory_delete_topic", {"topic_id": topic_id})


@mcp.tool()
def memory_add_relationship(from_topic_id: str, to_topic_id: str, kind: str) -> dict[str, Any]:
    """Add RELATED edge from_topic -> to_topic."""
    return _runner().execute(
        "memory_add_relationship",
        {"from_topic_id": from_topic_id, "to_topic_id": to_topic_id, "kind": kind},
    )


@mcp.tool()
def memory_remove_relationship(from_topic_id: str, to_topic_id: str, kind: str) -> dict[str, Any]:
    """Remove RELATED edge."""
    return _runner().execute(
        "memory_remove_relationship",
        {"from_topic_id": from_topic_id, "to_topic_id": to_topic_id, "kind": kind},
    )


@mcp.tool()
def memory_append_field(
    topic_id: str,
    field_name: str,
    value: Any = "",
    field_type: str = "string",
    ref_topic_id: str | None = None,
    why_changed: str | None = None,
    provenance: str = "mcp",
) -> dict[str, Any]:
    """Append history to a field; reuse an existing field_name when the fact fits—avoid redundant new fields."""
    args: dict[str, Any] = {
        "topic_id": topic_id,
        "field_name": field_name,
        "value": value,
        "field_type": field_type,
        "provenance": provenance,
    }
    if why_changed is not None:
        args["why_changed"] = why_changed
    if ref_topic_id is not None:
        args["ref_topic_id"] = ref_topic_id
    return _runner().execute("memory_append_field", args)


@mcp.tool()
def memory_get_field(
    topic_id: str,
    field_name: str,
    nested_field_name: str | None = None,
    with_history: bool = True,
) -> dict[str, Any]:
    """Read field: current value and revision history (newest first). Use nested_field_name for inner nested fields."""
    args: dict[str, Any] = {
        "topic_id": topic_id,
        "field_name": field_name,
        "with_history": with_history,
    }
    if nested_field_name:
        args["nested_field_name"] = nested_field_name
    return _runner().execute("memory_get_field", args)


@mcp.tool()
def memory_get_field_history(
    topic_id: str,
    field_name: str,
    nested_field_name: str | None = None,
) -> dict[str, Any]:
    """Read field current value and full revision history. Use when user asks for prior values or change timeline."""
    args: dict[str, Any] = {"topic_id": topic_id, "field_name": field_name}
    if nested_field_name:
        args["nested_field_name"] = nested_field_name
    return _runner().execute("memory_get_field_history", args)


@mcp.tool()
def memory_delete_field(topic_id: str, field_name: str) -> dict[str, Any]:
    """Delete a field from a topic."""
    return _runner().execute("memory_delete_field", {"topic_id": topic_id, "field_name": field_name})


@mcp.tool()
def memory_set_field_ref(topic_id: str, field_name: str, ref_topic_id: str = "") -> dict[str, Any]:
    """Set or clear field ref_topic_id (empty string clears)."""
    return _runner().execute(
        "memory_set_field_ref",
        {"topic_id": topic_id, "field_name": field_name, "ref_topic_id": ref_topic_id},
    )


@mcp.tool()
def memory_nest_fields_in_topic(
    topic_id: str,
    field_names: list[str],
    nest_key: str,
    provenance: str = "mcp",
) -> dict[str, Any]:
    """Group fields into one json bundle on the same topic (no new Topic node, no RELATED, no ref)."""
    return _runner().execute(
        "memory_nest_fields_in_topic",
        {"topic_id": topic_id, "field_names": field_names, "nest_key": nest_key, "provenance": provenance},
    )


@mcp.tool()
def memory_unnest_fields_in_topic(topic_id: str, nest_key: str) -> dict[str, Any]:
    """Expand a nested json bundle back to top-level fields."""
    return _runner().execute(
        "memory_unnest_fields_in_topic",
        {"topic_id": topic_id, "nest_key": nest_key},
    )


@mcp.tool()
def memory_promote_fields_to_nested_topic(
    parent_topic_id: str,
    field_names: list[str],
    child_title: str,
    child_summary: str | None = None,
    child_topic_id: str | None = None,
    child_topic_kind: str | None = None,
    relationship_kind: str = "has_detail",
    parent_link_field: str | None = None,
    link_provenance: str = "mcp",
    max_history: int = 500,
) -> dict[str, Any]:
    """Rare: new child Topic + RELATED (+ optional ref). Prefer memory_nest_fields_in_topic for same-topic nesting."""
    args: dict[str, Any] = {
        "parent_topic_id": parent_topic_id,
        "field_names": field_names,
        "child_title": child_title,
        "relationship_kind": relationship_kind,
        "link_provenance": link_provenance,
        "max_history": max_history,
    }
    if child_summary is not None:
        args["child_summary"] = child_summary
    if child_topic_id is not None:
        args["child_topic_id"] = child_topic_id
    if child_topic_kind is not None:
        args["child_topic_kind"] = child_topic_kind
    if parent_link_field is not None:
        args["parent_link_field"] = parent_link_field
    return _runner().execute("memory_promote_fields_to_nested_topic", args)


@mcp.tool()
def memory_undo_promote_nested_topic(
    parent_topic_id: str,
    child_topic_id: str,
    relationship_kind: str = "",
) -> dict[str, Any]:
    """Merge nested child fields back onto parent, remove edge and ref fields, delete child."""
    args: dict[str, Any] = {
        "parent_topic_id": parent_topic_id,
        "child_topic_id": child_topic_id,
    }
    if relationship_kind.strip():
        args["relationship_kind"] = relationship_kind.strip()
    return _runner().execute("memory_undo_promote_nested_topic", args)


@mcp.tool()
def memory_reorganize_consolidation(criteria: str = "") -> dict[str, Any]:
    """Consolidation: guidelines + topics_schema_snapshot (no values/histories)."""
    return _runner().execute("memory_reorganize_consolidation", {"criteria": criteria})


@mcp.tool()
def memory_reorganize_merge_topics(criteria: str = "") -> dict[str, Any]:
    """Merge topics: schema snapshot first; then compare current values (get_topic_schema current) for overlap—merge only if organization improves."""
    return _runner().execute("memory_reorganize_merge_topics", {"criteria": criteria})


@mcp.tool()
def memory_reorganize_split_topics(criteria: str = "") -> dict[str, Any]:
    """Split topics: guidelines + topics_schema_snapshot (structure only)."""
    return _runner().execute("memory_reorganize_split_topics", {"criteria": criteria})


@mcp.tool()
def memory_reorganize_connect_topics(criteria: str = "") -> dict[str, Any]:
    """Connect topics: guidelines + topics_schema_snapshot (structure only)."""
    return _runner().execute("memory_reorganize_connect_topics", {"criteria": criteria})


@mcp.tool()
def memory_reorganize_retention_trim(criteria: str = "") -> dict[str, Any]:
    """Retention trim (RTC): guidelines + topics_schema_snapshot (structure only)."""
    return _runner().execute("memory_reorganize_retention_trim", {"criteria": criteria})


@mcp.tool()
def study_unit_catalog() -> dict[str, Any]:
    """Study mode: precomputed unit hierarchy (empty unless catalog was attached to the runner)."""
    return _runner().execute("study_unit_catalog", {})


@mcp.tool()
def study_graph_snapshot(study_topic_kind: str) -> dict[str, Any]:
    """Study phase A: subgraph for topics with this topic_kind (e.g. study:<session_uuid>)."""
    r = MemoryToolRunner(get_store(), study_session_kind=study_topic_kind.strip())
    return r.execute("study_graph_snapshot", {})


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
