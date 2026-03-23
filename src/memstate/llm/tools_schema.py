"""OpenAI/Ollama-compatible tool definitions for MemState memory operations."""

from __future__ import annotations

from typing import Literal

OLLAMA_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "memory_graph_snapshot",
            "description": "Return the full topic graph: nodes (topics with summary fields) and edges (RELATED + field refs). Use to explore or answer questions about structure.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_list_topics",
            "description": "List topic id, title, short summary, topic_kind, and archived flag for each topic so you can choose which topic to open. topic_ids is also included for convenience. Optionally include archived topics.",
            "parameters": {
                "type": "object",
                "properties": {
                    "include_archived": {
                        "type": "boolean",
                        "description": "If true, include archived topics.",
                        "default": False,
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_get_topic_schema",
            "description": "Return the field schema for one topic without loading full topic metadata unless needed. Use detail level based on the question: minimal = field names and types only; current = same plus latest value per field; history = full revision history per field (same shape as memory_get_topic fields). Prefer minimal or current when exploring; use history only when the user asks about past values or provenance.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic_id": {"type": "string", "description": "Topic UUID"},
                    "detail": {
                        "type": "string",
                        "enum": ["minimal", "current", "history"],
                        "description": "minimal: field_type and ref_topic_id only. current: adds latest value per field. history: full history arrays per field.",
                        "default": "minimal",
                    },
                },
                "required": ["topic_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_get_topic",
            "description": "Load one topic by id with title, summary, kind, salience, archived flag, and all fields with history.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic_id": {
                        "type": "string",
                        "description": "Topic UUID",
                    }
                },
                "required": ["topic_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_create_topic",
            "description": "Create a new topic node.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Topic title"},
                    "summary": {"type": "string", "description": "Optional summary"},
                    "topic_kind": {"type": "string", "description": "Optional kind label e.g. project"},
                    "salience": {"type": "number", "description": "Salience weight", "default": 1.0},
                    "topic_id": {
                        "type": "string",
                        "description": "Optional UUID; random if omitted",
                    },
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_update_topic",
            "description": "Patch topic metadata (only set provided fields).",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic_id": {"type": "string"},
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "topic_kind": {"type": "string"},
                    "salience": {"type": "number"},
                    "archived": {"type": "boolean"},
                },
                "required": ["topic_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_delete_topic",
            "description": "Delete a topic permanently.",
            "parameters": {
                "type": "object",
                "properties": {"topic_id": {"type": "string"}},
                "required": ["topic_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_add_relationship",
            "description": "Add a RELATED edge from one topic to another with a kind string (e.g. associated_with, start_after).",
            "parameters": {
                "type": "object",
                "properties": {
                    "from_topic_id": {"type": "string"},
                    "to_topic_id": {"type": "string"},
                    "kind": {"type": "string", "description": "Relationship label"},
                },
                "required": ["from_topic_id", "to_topic_id", "kind"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_remove_relationship",
            "description": "Remove a RELATED edge.",
            "parameters": {
                "type": "object",
                "properties": {
                    "from_topic_id": {"type": "string"},
                    "to_topic_id": {"type": "string"},
                    "kind": {"type": "string"},
                },
                "required": ["from_topic_id", "to_topic_id", "kind"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_append_field",
            "description": "Append a new history entry to a field (creates the field if missing). Before choosing field_name, read existing fields (memory_get_topic_schema with detail current or memory_get_topic). Reuse an existing field_name when the new fact belongs there—same concept, correction, or update—instead of adding a redundant new field (e.g. append to married, not spouse_is_married). Use a new field_name only for a genuinely separate attribute.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic_id": {"type": "string"},
                    "field_name": {"type": "string"},
                    "value": {"description": "JSON-serializable value"},
                    "field_type": {
                        "type": "string",
                        "description": "string, json, list, int, float, bool, date, datetime",
                        "default": "string",
                    },
                    "ref_topic_id": {
                        "type": "string",
                        "description": "Optional UUID of another topic this field references",
                    },
                    "why_changed": {"type": "string"},
                    "provenance": {"type": "string", "default": "llm"},
                },
                "required": ["topic_id", "field_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_get_field",
            "description": "Read one field on a topic including history.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic_id": {"type": "string"},
                    "field_name": {"type": "string"},
                },
                "required": ["topic_id", "field_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_delete_field",
            "description": "Remove a named field from a topic.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic_id": {"type": "string"},
                    "field_name": {"type": "string"},
                },
                "required": ["topic_id", "field_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_set_field_ref",
            "description": "Set or clear field-level ref_topic_id (reference to another topic).",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic_id": {"type": "string"},
                    "field_name": {"type": "string"},
                    "ref_topic_id": {
                        "type": "string",
                        "description": "Target topic UUID or empty to clear",
                    },
                },
                "required": ["topic_id", "field_name"],
            },
        },
    },
]


def _tool_function_name(tool: dict) -> str:
    return str((tool.get("function") or {}).get("name") or "")


# Read / list only (query path).
QUERY_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "memory_graph_snapshot",
        "memory_list_topics",
        "memory_get_topic_schema",
        "memory_get_topic",
        "memory_get_field",
    }
)

# Writes + read helpers needed to resolve ids before writing (ingest path; no full graph snapshot).
INGEST_WRITE_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "memory_create_topic",
        "memory_update_topic",
        "memory_delete_topic",
        "memory_add_relationship",
        "memory_remove_relationship",
        "memory_append_field",
        "memory_delete_field",
        "memory_set_field_ref",
    }
)
INGEST_READ_HELPER_NAMES: frozenset[str] = frozenset(
    {
        "memory_list_topics",
        "memory_get_topic_schema",
        "memory_get_topic",
        "memory_get_field",
    }
)
INGEST_TOOL_NAMES: frozenset[str] = INGEST_WRITE_TOOL_NAMES | INGEST_READ_HELPER_NAMES

IntentRoute = Literal["query", "ingest", "both"]


def tools_for_intent_route(route: IntentRoute) -> list[dict]:
    """Subset of tools exposed to the LLM for the routed chat phase."""
    if route == "query":
        return [t for t in OLLAMA_TOOLS if _tool_function_name(t) in QUERY_TOOL_NAMES]
    if route == "ingest":
        return [t for t in OLLAMA_TOOLS if _tool_function_name(t) in INGEST_TOOL_NAMES]
    return list(OLLAMA_TOOLS)


INTENT_CLASSIFY_SYSTEM = """You classify the *latest user message* for a topic-graph memory assistant.

Reply with exactly one word on the first line (no punctuation, no explanation):
- query — Questions, listing, summarizing, retrieving facts, or exploring what is stored (read-only).
- ingest — Storing, adding, updating, deleting, linking, remembering, or changing stored facts.
- both — Needs both reading and writing in one turn (e.g. find a topic then add or change a field).

If unclear, reply: both"""


QUERY_ROUTE_PROMPT = """Routed mode: QUERY (read-only).
You only have read/list tools available. Answer from stored facts; do not attempt creates, updates, deletes, or relationship/field writes."""

INGEST_ROUTE_PROMPT = """Routed mode: INGEST (writes).
Use write tools to change memory. Use read helpers (list_topics, get_topic_schema, get_topic, get_field) only to resolve topic ids or inspect fields before writing. You do not have memory_graph_snapshot—use list_topics and get_topic* instead."""

BOTH_ROUTE_PROMPT = """Routed mode: BOTH (read and write).
You have the full tool set: read or write in any order as needed for the user's latest message."""


def build_chat_system_prompt(route: IntentRoute) -> str:
    """Full system prompt for /api/llm/chat after intent routing."""
    parts = [SYSTEM_PROMPT, INTENT_ROUTING_PROMPT]
    if route == "query":
        parts.append(QUERY_ROUTE_PROMPT)
    elif route == "ingest":
        parts.append(INGEST_ROUTE_PROMPT)
    else:
        parts.append(BOTH_ROUTE_PROMPT)
    return "\n\n".join(parts)


SYSTEM_PROMPT = """You control MemState, a topic graph memory store (Kuzu), in private—users should never hear product names, "tools", or database talk unless they asked.

Grounding (mandatory):
- You MUST use the memory_* tools to read or write data. Do not invent topic ids, titles, edges, or field values.
- Before answering anything about what is stored, call at least one read tool (e.g. memory_graph_snapshot, memory_list_topics, memory_get_topic_schema, or memory_get_topic).
- Use memory_list_topics to see ids with titles and summaries; use memory_get_topic_schema to inspect field names/types (and optionally current values or full history) without pulling the entire topic unless needed.
- Your final reply must be based only on what those tools returned (plus obvious paraphrase). If tools do not contain the answer, say you don't know or don't have that detail—without mentioning tools, databases, or "memory" as a system.
- For edits (create/update/delete/link/fields), call the appropriate tools, then confirm briefly using tool outcomes.
- If a tool returns ok:false or an error field, explain that to the user.

Field updates (when writing facts with memory_append_field):
- First inspect what is already on the topic (memory_get_topic_schema with detail current, or memory_get_topic). Do not invent a new field if the data fits an existing one.
- Prefer appending to the same field_name (new history entry) when you are updating, refining, or correcting the same kind of fact—e.g. status, role, location, marital status, dates—rather than splitting across synonyms (married vs is_married vs spouse).
- Create a new field_name only when the fact is a clearly separate attribute, or the user asked for a specific new key.
- Put narrative context in topic title/summary via memory_update_topic when appropriate; keep fields for structured facts.

Final answer to the user (tone and form):
- Speak as a person who simply *knows* things—not as software describing a database. Never narrate storage: avoid "the memory records…", "memory only contains…", "stored in memory", "based on my memory", "according to what I have in memory", or talking about "memory" as a separate thing. Do not echo JSON, tool names, or UUIDs unless the user asked for an id.
- Answer directly in plain first person (e.g. "Yes—Abdelghny is married."). No hedges like "based on the information", "according to the data", "as far as I can tell from…".
- If a detail was not in the tool results, answer like a human who doesn't know that piece (e.g. "I don't know when he married." or "I don't have a date—just that he's married."). Do not say the limitation is because "memory" or "the record" lacks a field; that sounds like an LLM reporting on a datastore.

When the client sends prior assistant replies in the thread, use them to resolve follow-ups; the latest user message is always what you must address."""

# Appended to SYSTEM_PROMPT for /api/llm/chat only (not MCP).
INTENT_ROUTING_PROMPT = """Dialogue intent (the messages after this block include recent user/assistant turns):
- Infer what the *latest user message* is trying to do before you choose tools: e.g. answer a question from stored facts, add or update stored facts, delete or link topics, follow-up that refers to earlier wording, or casual chat.
- Resolve references ("he", "she", "that", "it", "the same person") using the preceding turns you can see.
- Pick the smallest appropriate memory_* tool set for that intent; do not read the whole graph if a narrow query suffices."""
