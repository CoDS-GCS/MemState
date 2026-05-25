"""OpenAI/Ollama-compatible tool definitions for MemState memory operations."""

from __future__ import annotations

from typing import Literal

OLLAMA_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "memory_graph_snapshot",
            "description": (
                "Return the full topic graph: nodes (topics with summary fields) and edges (RELATED + field refs). "
                "Use to see how topics connect; then open linked topic ids with memory_get_topic_schema or memory_get_topic "
                "to walk the graph across multiple hops when one node is not enough to answer the question."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_list_topics",
            "description": (
                "List topic id, title, short summary, topic_kind, and archived flag for each topic. "
                "**Required before memory_create_topic on any ingest/write turn**—check whether a person, project, "
                "or group already exists and reuse that topic_id instead of creating a duplicate. "
                "After picking a topic, use get_topic_schema or get_topic; follow ref_topic_id and RELATED edges when needed."
            ),
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
            "name": "memory_topics_schema_page",
            "description": (
                "Paginated **schema-only** slice of topics: id, title, topic_kind, archived, salience, per-field "
                "field_type / ref_topic_id / salience / nested_field_names (for existing json bundles)—**no values, "
                "no histories, no edges**. Use to scan **all** topics in order: start offset=0, then set offset to "
                "next_offset until has_more is false. Prefer this over memory_list_topics + many get_topic_schema calls "
                "when deciding which topics need nesting or reorganization from structure alone."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "offset": {
                        "type": "integer",
                        "description": "Skip this many topics (stable sort by topic id)",
                        "default": 0,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Page size (max 50)",
                        "default": 15,
                    },
                    "include_archived": {
                        "type": "boolean",
                        "description": "Include archived topics in the id list",
                        "default": False,
                    },
                    "topic_kind": {
                        "type": "string",
                        "description": "If set, only topics with this topic_kind (Study mode may override)",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_get_topic_schema",
            "description": (
                "Return the field **schema** for one topic (structure only by default). "
                "Use detail=minimal first to see field names, types, and ref_topic_id without values. "
                "After choosing a field, call memory_get_field (current value + revision history) or memory_get_field_history when the user asks how a value changed or for prior values. For nested bundles, use nested_field_names from minimal schema, then memory_get_field with field_name=nest key and nested_field_name=inner name (or pass the inner name as field_name for auto-resolve). "
                "Use memory_get_topic only when you need every field with full history on one topic. "
                "ref_topic_id on a field points at another topic—follow with get_topic_schema (minimal) or memory_get_field on linked topics. "
                "Use detail=current or history only when you must bulk-load values on this topic without per-field reads."
            ),
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
            "description": (
                "Load one topic by id with title, summary, kind, salience, archived flag, and all fields with history. "
                "If a field has ref_topic_id, call get_topic (or get_topic_schema) again on that id to traverse the graph until you have the facts you need."
            ),
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
            "description": (
                "Create a **new** topic only when memory_list_topics confirms no existing topic matches the same person, "
                "project, group, or subject (compare titles and summaries). If a match exists, do **not** call this—use "
                "memory_update_topic, memory_append_field, and memory_add_relationship on the existing topic_id instead. "
                "Use only for substantial new subjects not already in the graph. Do not use for small facts—append fields on "
                "an existing topic instead."
            ),
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
            "description": "Append a new history entry to a field (creates the field if missing). You MUST pass `value` with the fact to store—calls without `value` are rejected. Before choosing field_name, read existing fields (memory_get_topic_schema with detail current or memory_get_topic). Reuse an existing field_name when the new fact belongs there—same concept, correction, or update—instead of adding a redundant new field (e.g. append to married, not spouse_is_married). Use a new field_name only for a genuinely separate attribute (e.g. place_of_birth / birth_place for town+city even if birth_country already exists).",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic_id": {"type": "string"},
                    "field_name": {"type": "string"},
                    "value": {
                        "description": "The fact to store (string, number, bool, list, or object). Required—use \"\" only if intentionally clearing text.",
                    },
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
                "required": ["topic_id", "field_name", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_get_field",
            "description": (
                "Read one field on a topic: returns current `value` and full revision `history` (newest first). "
                "Each history entry has value, valid_from, why_changed, provenance, and optional operation. "
                "Use when you need the latest value or a single field's timeline. "
                "For nested inner fields use nested_field_name + field_name=nest key, or pass the inner name as field_name (auto-resolved). "
                "Set with_history=false to fetch only the current value. "
                "When the user explicitly asks for past values or change history, prefer memory_get_field_history."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic_id": {"type": "string"},
                    "field_name": {
                        "type": "string",
                        "description": "Top-level field name, or nest bundle key when reading a nested inner field",
                    },
                    "nested_field_name": {
                        "type": "string",
                        "description": "Inner field inside a json nest bundle (requires field_name = nest key)",
                    },
                    "with_history": {
                        "type": "boolean",
                        "description": "If false, return only current value (omit history array). Default true.",
                        "default": True,
                    },
                },
                "required": ["topic_id", "field_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_get_field_history",
            "description": (
                "Read one field's current value and full revision history (same as memory_get_field with with_history=true). "
                "Use when the user asks how a fact changed over time, what it used to be, when it was updated, or for prior values. "
                "History is newest-first; history[0] matches field.value. "
                "Supports nested inner fields via nested_field_name or auto-resolve by inner field_name."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic_id": {"type": "string"},
                    "field_name": {
                        "type": "string",
                        "description": "Top-level or inner nested field name",
                    },
                    "nested_field_name": {
                        "type": "string",
                        "description": "Inner field inside a json nest bundle (requires field_name = nest key)",
                    },
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
    {
        "type": "function",
        "function": {
            "name": "memory_nest_fields_in_topic",
            "description": (
                "**Default nesting:** group related fields **inside the same topic** as one `json` bundle—no new graph "
                "node, no RELATED edge, no ref_topic_id. Top-level fields are removed and stored under `nest_key` with "
                "full per-field histories preserved inside the bundle. The graph shows one topic; the UI shows nested "
                "fields under that key. Undo with memory_unnest_fields_in_topic. Do **not** use this to split unrelated "
                "subjects (use memory_reorganize_split_topics + new topics for that)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic_id": {"type": "string", "description": "Topic to group fields on"},
                    "field_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Existing top-level field names to fold into the bundle (at least one)",
                    },
                    "nest_key": {
                        "type": "string",
                        "description": "New field name for the json bundle (must not exist yet)",
                    },
                    "provenance": {"type": "string", "default": "llm"},
                },
                "required": ["topic_id", "field_names", "nest_key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_unnest_fields_in_topic",
            "description": (
                "Undo memory_nest_fields_in_topic: restore inner fields to the top level of the same topic and remove "
                "the bundle field."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic_id": {"type": "string"},
                    "nest_key": {"type": "string", "description": "The json bundle field name"},
                },
                "required": ["topic_id", "nest_key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_promote_fields_to_nested_topic",
            "description": (
                "**Rare / advanced only:** creates a **separate child Topic** node, RELATED parent→child, and optionally "
                "`parent_link_field` (ref_topic_id)—this **splits** the graph. For normal “nested detail under one "
                "subject”, use **memory_nest_fields_in_topic** instead (same topic, nested json, no new node, no ref). "
                "Study section→detail may still use this with `study_child` when a real child topic is required."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "parent_topic_id": {"type": "string", "description": "Topic to take fields from"},
                    "field_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Field names to move (at least one; must exist on parent)",
                    },
                    "child_title": {"type": "string", "description": "Title for the new nested topic"},
                    "child_summary": {
                        "type": "string",
                        "description": "Optional summary for the child topic",
                    },
                    "child_topic_id": {
                        "type": "string",
                        "description": "Optional UUID for the child; random if omitted",
                    },
                    "child_topic_kind": {
                        "type": "string",
                        "description": "Optional kind for the child; defaults to parent's topic_kind when omitted",
                    },
                    "relationship_kind": {
                        "type": "string",
                        "description": "RELATED edge from parent to child (default has_detail)",
                        "default": "has_detail",
                    },
                    "parent_link_field": {
                        "type": "string",
                        "description": "If set, append this field on the parent with ref_topic_id = child (must not be a moved name)",
                    },
                    "link_provenance": {
                        "type": "string",
                        "description": "Provenance for the optional parent link field revision",
                        "default": "llm",
                    },
                    "max_history": {
                        "type": "integer",
                        "description": "History cap when creating parent link field",
                        "default": 500,
                    },
                },
                "required": ["parent_topic_id", "field_names", "child_title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_undo_promote_nested_topic",
            "description": (
                "Undo memory_promote_fields_to_nested_topic: merge the child's fields back onto the parent, remove the "
                "parent→child RELATED edge and any parent fields whose ref_topic_id pointed at the child, then delete "
                "the child topic. Fails if the parent already has a field with the same name as one on the child."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "parent_topic_id": {"type": "string"},
                    "child_topic_id": {"type": "string"},
                    "relationship_kind": {
                        "type": "string",
                        "description": "RELATED kind from parent to child; omit if only one such edge exists",
                    },
                },
                "required": ["parent_topic_id", "child_topic_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_reorganize_consolidation",
            "description": (
                "Reorganization: consolidation. Returns guidelines and topics_schema_snapshot (field names, types, "
                "refs, salience, RELATED edges only—no field values or histories). Plan from structure; use "
                "memory_get_topic_schema / memory_get_topic only when values are needed before writes. Then apply "
                "with write tools."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "criteria": {
                        "type": "string",
                        "description": "User goals (size, performance, reasoning).",
                        "default": "",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_reorganize_merge_topics",
            "description": (
                "Reorganization: merge topics. Returns guidelines and topics_schema_snapshot (structure only). "
                "Use schema overlap (field names/types, kinds, titles, refs) to propose candidates; then call "
                "memory_get_topic_schema with detail current (or memory_get_topic) on candidates to compare **values**—"
                "overlap and intersection (e.g. shared list items, same strings, same entity). Merge only if merging "
                "improves organization; skip merges that would blur distinct entities."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "criteria": {
                        "type": "string",
                        "description": "User goals for merging.",
                        "default": "",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_reorganize_split_topics",
            "description": (
                "Reorganization: split overloaded topics into **separate** subjects (new or existing topics). Returns "
                "guidelines and topics_schema_snapshot (structure only). For **grouping related fields inside one "
                "topic** without a new graph node, use memory_nest_fields_in_topic—not this tool."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "criteria": {
                        "type": "string",
                        "description": "User goals for splitting.",
                        "default": "",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_reorganize_connect_topics",
            "description": (
                "Reorganization: connect topics with RELATED edges or refs. Returns guidelines and "
                "topics_schema_snapshot (structure only)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "criteria": {
                        "type": "string",
                        "description": "User goals for linking.",
                        "default": "",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_reorganize_retention_trim",
            "description": (
                "Reorganization: retention trim (RTC). Returns guidelines and topics_schema_snapshot (structure "
                "only). Plan from salience, archived, field counts—use history tools only when trimming revisions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "criteria": {
                        "type": "string",
                        "description": "User goals for retention.",
                        "default": "",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "study_unit_catalog",
            "description": (
                "Study mode (phase A): returns the precomputed hierarchical unit catalog (levels coarse/medium/fine) "
                "with token counts and neighbor context. Use when the prompt catalog was truncated."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "study_graph_snapshot",
            "description": (
                "Study mode (phase A): graph snapshot for this Study session only (topic_kind study:<session_id>). "
                "Same shape as the UI graph; edges only between session topics. Do not use memory_graph_snapshot in phase A."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
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
        "memory_topics_schema_page",
        "memory_get_topic_schema",
        "memory_get_topic",
        "memory_get_field",
        "memory_get_field_history",
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
        "memory_nest_fields_in_topic",
        "memory_unnest_fields_in_topic",
        "memory_promote_fields_to_nested_topic",
        "memory_undo_promote_nested_topic",
    }
)
INGEST_READ_HELPER_NAMES: frozenset[str] = frozenset(
    {
        "memory_list_topics",
        "memory_topics_schema_page",
        "memory_get_topic_schema",
        "memory_get_topic",
        "memory_get_field",
        "memory_get_field_history",
        "memory_reorganize_consolidation",
        "memory_reorganize_merge_topics",
        "memory_reorganize_split_topics",
        "memory_reorganize_connect_topics",
        "memory_reorganize_retention_trim",
    }
)
INGEST_TOOL_NAMES: frozenset[str] = INGEST_WRITE_TOOL_NAMES | INGEST_READ_HELPER_NAMES

# Study phase A: ingest writes + targeted reads + study helpers; no full graph, no reorganize.
STUDY_PHASE_A_TOOL_NAMES: frozenset[str] = frozenset(
    INGEST_WRITE_TOOL_NAMES
    | {
        "memory_list_topics",
        "memory_topics_schema_page",
        "memory_get_topic_schema",
        "memory_get_topic",
        "memory_get_field",
        "memory_get_field_history",
        "study_unit_catalog",
        "study_graph_snapshot",
    }
)

IntentRoute = Literal["query", "ingest", "both"]


def tools_for_intent_route(route: IntentRoute) -> list[dict]:
    """Subset of tools exposed to the LLM for the routed chat phase."""
    if route == "query":
        return [t for t in OLLAMA_TOOLS if _tool_function_name(t) in QUERY_TOOL_NAMES]
    if route == "ingest":
        return [t for t in OLLAMA_TOOLS if _tool_function_name(t) in INGEST_TOOL_NAMES]
    return list(OLLAMA_TOOLS)


def tools_for_study_phase_a() -> list[dict]:
    return [t for t in OLLAMA_TOOLS if _tool_function_name(t) in STUDY_PHASE_A_TOOL_NAMES]


INTENT_CLASSIFY_SYSTEM = """You classify the *latest user message* for a topic-graph memory assistant.

Reply with exactly one word on the first line (no punctuation, no explanation):
- query — Questions, listing, summarizing, retrieving facts, or exploring what is stored (read-only).
- ingest — Storing, adding, updating, deleting, linking, remembering, or changing stored facts.
- both — Needs both reading and writing in one turn (e.g. find a topic then add or change a field).

If unclear, reply: both"""


QUERY_ROUTE_PROMPT = """Routed mode: QUERY (read-only).
You only have read/list tools available. Answer from stored facts; do not attempt creates, updates, deletes, or relationship/field writes.
Each returned field includes salience (0–10); on this path, accessed fields are bumped slightly (capped) and the topic salience is updated to the average of field saliences.

Graph traversal: You may and should issue multiple read calls in sequence to walk the topic graph. Topics link via RELATED edges and via field ref_topic_id (see memory_graph_snapshot). If the answer is not fully on one topic, follow those links: open related topic ids with memory_get_topic_schema (detail minimal) or memory_get_topic, then use memory_get_field for specific field values and history (use nested_field_name for inner fields inside json nest bundles). When the user asks how a value changed or what it used to be, call memory_get_field_history on that field. Use memory_graph_snapshot or memory_list_topics to orient, then drill into topics and their neighbors until you have enough detail. Do not stop after a single topic when the question depends on linked people, projects, or other entities."""

INGEST_ROUTE_PROMPT = """Routed mode: INGEST (writes).
Use write tools to change memory. Use read helpers (list_topics, get_topic_schema, get_topic, get_field) only to resolve topic ids or inspect fields before writing. You do not have memory_graph_snapshot—use list_topics and get_topic* instead.

**Before any write:** Call memory_list_topics (or memory_topics_schema_page) to resolve existing topic ids for people, projects, and groups mentioned in the message. **Never create a second topic for the same real-world entity** already in the list—update that topic with memory_append_field, memory_update_topic, and memory_add_relationship instead.

**Classify what the user sent, then pick tools:**
1) **Field value** — Small fact, correction, attribute, or snippet that belongs on an **existing** topic. Use memory_append_field (reuse field_name when the kind of fact matches) and/or memory_update_topic for title/summary narrative. **Do not** call memory_create_topic.
2) **Nested / not ready for its own topic** — Subordinate detail that should stay **inside** a parent topic: store as one or more fields (string, json, list—including ordered lists of ids). This is “embedded” material until it is big enough or shared enough to promote. Still **no** memory_create_topic unless the user clearly introduces a **new** standalone subject.
3) **Separate topic** — Use memory_create_topic only when the content is a **non-trivial, coherent** new subject (or a large multi-fact unit) **and** memory_list_topics shows no matching title yet. Skip new topics for trivia and thin one-offs.

**Small-knowledge rule:** If it fits a line or two and is not a new domain, merge into an existing topic as fields or summary—never mint a topic just to “save” a minor fact.

**Multi-entity messages:** When the user mentions themselves plus other people plus a project (e.g. “Essam and I are working on MemState”), reuse existing person/project topics from list_topics, create **only** subjects that are genuinely new (e.g. MemState if absent), then link with memory_add_relationship and field refs—do not recreate Abdelghny or Essam if they already exist.

Large inputs: When there are **several distinct substantial themes**, split across topics (one coherent entity, section, or theme per topic), link with memory_add_relationship and ref_topic_id where helpful. Avoid splitting into **micro-topics**; keep minor points as fields inside the right parent.
If the user message is labeled Part i/n with overlap between parts, treat it as one ingest task in sequence: merge with prior parts without duplicating the same entities or facts."""

BOTH_ROUTE_PROMPT = """Routed mode: BOTH (read and write).
You have the full tool set: read or write in any order as needed for the user's latest message. When answering from stored facts, traverse the graph (RELATED edges and field refs) with repeated reads as in query mode until you have enough detail—do not assume one topic is enough if the question spans linked entities.

When **storing**, call memory_list_topics first to resolve existing ids. Apply the same ingest classification as ingest-only mode: (1) field value on an existing topic, (2) nested content as fields on a parent—not memory_create_topic, (3) separate topic only for substantial new subjects **not already in list_topics**. **Do not create topics for small knowledge or duplicate people/projects already stored.**

When the user is storing a **large** amount of new information across **distinct substantial themes**, split across topics and link them—avoid one overloaded topic and avoid micro-topics.
If the user message is labeled Part i/n with overlap between parts, continue one task across chunks without duplicating entities or facts."""

REORGANIZE_PROMPT = """Memory reorganize (hierarchical—avoid loading everything at once):
1) Call the matching memory_reorganize_* tool for the user’s goal (consolidation, merge_topics, split_topics, connect_topics, retention_trim) with their criteria. That returns topics_schema_snapshot: structure only (field names/types, edges)—no full values or histories.
2) Plan from that snapshot first. Do not call memory_graph_snapshot or bulk list_topics unless the snapshot is insufficient.
3) **Merge topics exception:** For memory_reorganize_merge_topics, after the schema pass you **must** compare **current field values** for candidate pairs (memory_get_topic_schema with detail current, or memory_get_topic). Look for value overlap and intersection (shared strings, list overlap, same facts). Merge **only if** merging improves organization; reject merges that would combine distinct entities.
4) For other reorganize modes, if you need a specific value or id, use memory_get_topic_schema (detail minimal or current) or a targeted memory_get_topic / memory_get_field—one topic at a time, not the whole graph.
5) Apply changes with write tools, then summarize briefly for the user without dumping tool names or UUIDs unless asked.

Use read tools in whatever order fits: the reorganize snapshot first, then targeted reads; for merge, schema then values then decide."""


TOPIC_VS_ENTITY_PROMPT = """Topic vs entity (how to package memory):
- A **topic** is the unit of storage: one self-contained record (metadata + fields_json). MemState has no separate Entity node type.
- Informal **entities** (people, papers, concepts, etc.) often live **inside** a single topic as **field values** while they stay small, local, and not heavily referenced from elsewhere in the graph.
- **Do not create a topic for small knowledge** (one-liners, tiny facts, minor updates). Prefer memory_append_field or memory_update_topic on the best matching **existing** topic.
- **Grouping related fields under one subject** (e.g. professional details) should use **memory_nest_fields_in_topic**—one json bundle on the **same** topic, no new graph node, no RELATED, no ref. Scan candidates with **memory_topics_schema_page** (paginate with offset/next_offset) before asking for values. Do **not** default to memory_promote_fields_to_nested_topic (that creates a **separate** Topic—only for rare cases or Study `study_child` when a real child topic is required).
- **Create another topic** when something is **substantial and standalone**, grows complex, is linked from **many** topics, or needs its own revision and provenance at graph granularity—then connect with RELATED and/or ref_topic_id on a field (same idea as docs-site data-model overview)."""


NO_DUPLICATE_TOPICS_PROMPT = """Do not duplicate topics (mandatory on ingest/write):
1) **First tool on any write turn:** memory_list_topics (or memory_topics_schema_page). Read every title and summary.
2) **Match before create:** If the message mentions a person, project, lab, group, or product already in that list (same name, same role, or obvious same entity), use the **existing topic_id**. Update with memory_append_field, memory_update_topic, memory_set_field_ref, and memory_add_relationship—**never** memory_create_topic for that entity again.
3) **memory_create_topic is only for subjects absent from list_topics** after you checked. One real-world entity = one topic in the graph.
4) **Multi-entity messages** (e.g. "Essam and I are working on MemState"): map each name to an existing topic when present; create at most the genuinely new project/topic; link collaborators with RELATED edges and field refs—do not mint second copies of people already stored.
5) **Self-reference ("I", "my"):** Resolve to the user's existing person topic from list_topics or prior turns, not a new topic unless none exists."""


def build_chat_system_prompt(route: IntentRoute) -> str:
    """Full system prompt for /api/llm/chat after intent routing."""
    parts = [SYSTEM_PROMPT, TOPIC_VS_ENTITY_PROMPT, INTENT_ROUTING_PROMPT]
    if route == "query":
        parts.append(QUERY_ROUTE_PROMPT)
    elif route == "ingest":
        parts.append(NO_DUPLICATE_TOPICS_PROMPT)
        parts.append(INGEST_ROUTE_PROMPT)
        parts.append(REORGANIZE_PROMPT)
    else:
        parts.append(NO_DUPLICATE_TOPICS_PROMPT)
        parts.append(BOTH_ROUTE_PROMPT)
        parts.append(REORGANIZE_PROMPT)
    return "\n\n".join(parts)


STUDY_PHASE_A_PROMPT = """Study mode — phase A (sandbox ingest only).
You are materializing a long document into new topics that are **isolated** from the rest of memory until phase B.
- Use the unit catalog (coarse / medium / fine) to choose granularity: use finer units where detail matters; coarser where content is redundant or structural only.
- Create topics for **catalog units** with clear titles and summaries; put supporting detail **in fields** (not extra topics) when a unit is small or purely subordinate—avoid micro-topics for sentences that belong inside one unit’s fields.
- **Only** connect topics that share this Study session’s topic_kind. Use memory_add_relationship with RELATED between siblings or sequence; use kind `study_child` from a **section** parent to a **detail** child when you need one level of nesting—never chain study_child deeper (no grandchild sections).
- Do **not** link to any topic outside this session. Do not call memory_graph_snapshot—use study_graph_snapshot.
- You may call study_unit_catalog if the catalog in the message was truncated."""


STUDY_PHASE_B_PROMPT = """Study mode — phase B (integrate with existing memory).
The user’s long document was ingested in phase A as Study topics (topic_kind study:<session_id>). Your job now:
- Link these topics to existing memory where appropriate (memory_add_relationship, field ref_topic_id).
- Use memory_reorganize_* helpers as needed, then apply writes: merge duplicates, consolidate, connect patterns—same discipline as normal reorganize (compare values before merge).
- Optionally set topic_kind via memory_update_topic to a normal label (e.g. notes) when a topic is fully integrated, or leave study:… as provenance."""


def build_study_phase_a_system_prompt(route: IntentRoute) -> str:
    """Phase A: sandbox tools; route should be ingest or both (writes)."""
    parts = [SYSTEM_PROMPT, TOPIC_VS_ENTITY_PROMPT, STUDY_PHASE_A_PROMPT, INTENT_ROUTING_PROMPT]
    if route == "ingest":
        parts.append(NO_DUPLICATE_TOPICS_PROMPT)
        parts.append(INGEST_ROUTE_PROMPT)
    elif route == "both":
        parts.append(NO_DUPLICATE_TOPICS_PROMPT)
        parts.append(BOTH_ROUTE_PROMPT)
    return "\n\n".join(parts)


def build_study_phase_b_system_prompt(route: IntentRoute) -> str:
    """Phase B: full graph + reorganize; same route as the original intent."""
    parts = [SYSTEM_PROMPT, TOPIC_VS_ENTITY_PROMPT, STUDY_PHASE_B_PROMPT, INTENT_ROUTING_PROMPT]
    if route == "query":
        parts.append(QUERY_ROUTE_PROMPT)
    elif route == "ingest":
        parts.append(NO_DUPLICATE_TOPICS_PROMPT)
        parts.append(INGEST_ROUTE_PROMPT)
        parts.append(REORGANIZE_PROMPT)
    else:
        parts.append(NO_DUPLICATE_TOPICS_PROMPT)
        parts.append(BOTH_ROUTE_PROMPT)
        parts.append(REORGANIZE_PROMPT)
    return "\n\n".join(parts)


SYSTEM_PROMPT = """You control MemState, a topic graph memory store (Kuzu), in private—users should never hear product names, "tools", or database talk unless they asked.

Grounding (mandatory):
- You MUST use the memory_* tools to read or write data. Do not invent topic ids, titles, edges, or field values.
- Brief greetings or tiny talk may be answered without tools. For anything about what is stored, or any edit, use the appropriate memory_* tools.
- Before answering anything about what is stored, call at least one read tool (e.g. memory_graph_snapshot, memory_list_topics, memory_get_topic_schema, or memory_get_topic).
- Use memory_list_topics to see ids with titles and summaries; use memory_get_topic_schema to inspect field names/types (detail minimal first; detail=current for latest values only; detail=history for all fields' histories on one topic).
- **Field history:** Every stored fact is a field with a value-only revision timeline (newest first). `memory_get_field` returns current `value` plus `history` for one field; `memory_get_field_history` is the dedicated read when the user asks for prior values, change over time, or "when did X change". Do not answer history questions from detail=current schema alone—call get_field or get_field_history on the specific field.
- The store is a graph: topics link via RELATED edges and field ref_topic_id. When answering from stored facts, follow those links with additional reads on the linked topic ids until you have what you need—do not treat one topic as always sufficient.
- Your final reply must be based only on what those tools returned (plus obvious paraphrase). If tools do not contain the answer, say you don't know or don't have that detail—without mentioning tools, databases, or "memory" as a system.
- For edits (create/update/delete/link/fields), call the appropriate tools, then confirm briefly using tool outcomes.
- If a tool returns ok:false or an error field, explain that to the user.
- **Never duplicate topics:** Before memory_create_topic, call memory_list_topics and reuse existing topic ids for the same person, project, or group. Creating a second topic for an entity already in the graph is wrong—update the existing one instead.

Field updates (when writing facts with memory_append_field):
- Every memory_append_field call MUST include `value` with the exact fact to store. If the tool returns an error about a missing value, fix the call and retry—do not tell the user it was saved.
- First inspect what is already on the topic (memory_get_topic_schema with detail current, or memory_get_topic). Do not invent a new field if the data fits an existing one.
- Prefer appending to the same field_name (new history entry) when you are updating, refining, or correcting the same kind of fact—e.g. status, role, location, marital status, dates—rather than splitting across synonyms (married vs is_married vs spouse).
- Create a new field_name only when the fact is a clearly separate attribute, or the user asked for a specific new key.
- **Birth / hometown:** If the user names a **town or city** (e.g. “born in Bshbish, Egypt”), store the full phrase in a dedicated field such as `birth_place` or `place_of_birth`. Do not treat `birth_country` alone as sufficient—town-level detail is new information.
- Put narrative context in topic title/summary via memory_update_topic when appropriate; keep fields for structured facts.
- On ingest, default small or nested material to **fields on an existing topic**; use memory_create_topic only for substantial new subjects (see routed ingest instructions when in ingest/both mode).
- To **organize** many related fields on one topic without adding graph nodes, use **memory_nest_fields_in_topic** (not memory_promote_fields_to_nested_topic unless a separate child Topic is explicitly required).

Final answer to the user (tone and form):
- Speak as a person who simply *knows* things—not as software describing a database. Never narrate storage: avoid "the memory records…", "memory only contains…", "stored in memory", "based on my memory", "according to what I have in memory", or talking about "memory" as a separate thing. Do not echo JSON, tool names, or UUIDs unless the user asked for an id.
- Answer directly in plain first person (e.g. "Yes—Abdelghny is married."). No hedges like "based on the information", "according to the data", "as far as I can tell from…".
- If a detail was not in the tool results, answer like a human who doesn't know that piece (e.g. "I don't know when he married." or "I don't have a date—just that he's married."). Do not say the limitation is because "memory" or "the record" lacks a field; that sounds like an LLM reporting on a datastore.

When the client sends prior assistant replies in the thread, use them to resolve follow-ups; the latest user message is always what you must address."""

# Appended to SYSTEM_PROMPT for /api/llm/chat only (not MCP).
INTENT_ROUTING_PROMPT = """Dialogue intent (the messages after this block include recent user/assistant turns):
- Infer what the *latest user message* is trying to do before you choose tools: e.g. answer a question from stored facts, add or update stored facts, delete or link topics, follow-up that refers to earlier wording, or casual chat.
- Resolve references ("he", "she", "that", "it", "the same person") using the preceding turns you can see.
- Pick the smallest appropriate memory_* tool set for that intent; avoid loading irrelevant bulk, but traverse relationships and field refs when the answer requires more than one topic."""

# Groq/Ollama runners when callers pass system_prompt=None (not the full chat API stack).
DEFAULT_LLM_SYSTEM_PROMPT_FALLBACK = "\n\n".join((SYSTEM_PROMPT, TOPIC_VS_ENTITY_PROMPT))
