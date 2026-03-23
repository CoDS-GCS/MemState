"""MCP stdio server exposing the same memory tools as the UI chat (for Claude Desktop, etc.)."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from memstate.llm.tool_runner import MemoryToolRunner
from memstate.store.graph_store import get_store

mcp = FastMCP(
    "memstate-memory",
    instructions=(
        "MemState topic graph memory: use these tools to read and edit topics, fields, "
        "and RELATED relationships. Call memory_graph_snapshot to see the full graph."
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
    """Create a new topic."""
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
    """Append a field value / history entry."""
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
def memory_get_field(topic_id: str, field_name: str) -> dict[str, Any]:
    """Read field with history."""
    return _runner().execute("memory_get_field", {"topic_id": topic_id, "field_name": field_name})


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


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
