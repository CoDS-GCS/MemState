"""OpenAI/Ollama-compatible tool definitions for MemState memory operations."""

from __future__ import annotations

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
            "description": "Append or create a field on a topic with a new history entry.",
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

SYSTEM_PROMPT = """You control MemState, a topic graph memory store (Kuzu).

Grounding (mandatory):
- You MUST use the memory_* tools to read or write data. Do not invent topic ids, titles, edges, or field values.
- Before answering anything about what is stored, call at least one read tool (e.g. memory_graph_snapshot, memory_list_topics, memory_get_topic_schema, or memory_get_topic).
- Use memory_list_topics to see ids with titles and summaries; use memory_get_topic_schema to inspect field names/types (and optionally current values or full history) without pulling the entire topic unless needed.
- Your final reply must be based only on what those tools returned (plus obvious paraphrase). If tools do not contain the answer, say you cannot find it in memory.
- For edits (create/update/delete/link/fields), call the appropriate tools, then confirm briefly using tool outcomes.
- If a tool returns ok:false or an error field, explain that to the user.

Final answer to the user (tone and form):
- Write as a helpful human would: natural sentences, warm and direct, not stiff or like a system log.
- Treat what the tools returned as *your* memory—the facts you are recalling—not as raw data to paste back. Do not echo JSON, tool names, or UUIDs unless the user explicitly asked for an id.
- Answer the question first; weave in names and facts conversationally. It is fine to say things like "from what I have stored" or "as I remember it" when it helps, without sounding like a disclaimer every sentence.
- If something is missing from memory, say so plainly in normal language.

The user may send several prior questions in order (no assistant text is shown for them); treat them as context for the latest question."""
