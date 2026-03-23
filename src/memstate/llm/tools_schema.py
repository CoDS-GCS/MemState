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
            "description": "List topic UUIDs. Optionally include archived topics.",
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
Use the provided tools to read or change topics, fields, and relationships.
Prefer memory_graph_snapshot or memory_list_topics to discover ids before other calls.
After mutating data, briefly confirm what changed. If a tool returns ok:false, explain the error."""
