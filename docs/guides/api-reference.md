# API reference

Interactive docs are available at `http://127.0.0.1:8765/docs` when the server is running.

All endpoints except `/health`, `/health/graph`, `/health/falkordb`, and `/` require authentication when `MEMSTATE_API_KEY` is set. See [Authentication](authentication.md).

For a route index with module ownership, see [HTTP endpoint index (HTML)](../api/index.html).

---

## Health

### `GET /health`

Liveness check. No auth required.

**Response `200`**

```json
{ "status": "ok" }
```

---

### `GET /health/graph`

Verifies the embedded Kuzu store opens and responds. No auth required.

**Response `200`**

```json
{ "status": "ok", "backend": "kuzu", "path": "memstate.kuzu" }
```

**Response `503`** — store unavailable

```json
{
  "status": "error",
  "error": "...",
  "path": "memstate.kuzu",
  "hint": "..."
}
```

---

### `GET /health/falkordb`

Backward-compatible alias for `GET /health/graph`.

---

## Ingest & query

### `POST /v1/ingest`

Ingest structured data into the topic graph. Triggers a background reasoner pass after completion.

**Request body** — `IngestRequest` (see `src/memstate/core/models.py`)

**Response `200`** — `IngestResponse`

---

### `POST /v1/query`

Query the topic graph. Triggers a background reasoner pass after completion.

**Request body** — `QueryRequest`

**Response `200`** — `QueryResponse`

---

## UI / graph

### `GET /api/ui/graph`

Returns a graph snapshot (nodes, edges, community IDs) for the D3 visualizer.

**Response `200`**

```json
{
  "nodes": [...],
  "edges": [...]
}
```

---

### `GET /api/ui/datamodel`

Returns the Mermaid source string for the data-model diagram.

**Response `200`**

```json
{ "mermaid": "flowchart LR\n  ..." }
```

---

### `GET /api/ui/system-context`

Returns the configured fixed system role / runtime context, if any.

**Response `200`**

```json
{
  "configured": true,
  "system_context": {
    "system_role": "...",
    "runtime_context": "..."
  }
}
```

---

### `PUT /api/ui/system-context`

Sets or updates the fixed system role and runtime context injected into every LLM prompt. Requires `X-Admin-Key` when a config already exists and `MEMSTATE_ADMIN_KEY` (or `MEMSTATE_API_KEY`) is set.

**Request body**

```json
{
  "system_role": "You are a knowledge assistant.",
  "runtime_context": "Running in a research environment."
}
```

**Response `200`** — same shape as `GET /api/ui/system-context`

---

## Topics

### `GET /api/ui/topics`

Lists all topic IDs.

| Query param | Type | Default | Description |
|---|---|---|---|
| `include_archived` | `bool` | `false` | Include archived topics. |

**Response `200`**

```json
{ "topic_ids": ["uuid-1", "uuid-2"] }
```

---

### `POST /api/ui/topics`

Creates a new topic.

**Request body**

```json
{
  "title": "My topic",
  "summary": "Optional summary.",
  "topic_kind": "note",
  "salience": 1.0,
  "topic_id": null
}
```

**Response `200`**

```json
{ "topic_id": "generated-or-supplied-uuid" }
```

---

### `GET /api/ui/topics/{topic_id}`

Returns full topic data including fields and history.

**Response `200`**

```json
{
  "id": "...",
  "title": "...",
  "summary": "...",
  "topic_kind": "...",
  "salience": 1.0,
  "failed_salience": 0.0,
  "archived": false,
  "fields": {
    "field_name": {
      "field_type": "string",
      "ref_topic_id": null,
      "history": [...]
    }
  },
  "topic_history": [...],
  "created_at": "...",
  "updated_at": "..."
}
```

**Response `404`** — topic not found

---

### `PATCH /api/ui/topics/{topic_id}`

Partially updates topic metadata. Omit any field to leave it unchanged.

**Request body**

```json
{
  "title": "Updated title",
  "summary": null,
  "topic_kind": null,
  "salience": null,
  "archived": null
}
```

**Response `200`**

```json
{ "topic_id": "..." }
```

---

### `DELETE /api/ui/topics/{topic_id}`

Deletes a topic and its edges.

**Response `200`**

```json
{ "deleted": "topic-uuid" }
```

---

## Relationships

### `POST /api/ui/topics/{from_id}/relationships`

Adds a typed `RELATED` edge between two topics.

**Request body**

```json
{
  "to_topic_id": "target-uuid",
  "kind": "associated_with"
}
```

**Response `200`**

```json
{ "ok": "true" }
```

---

### `DELETE /api/ui/topics/{from_id}/relationships`

Removes a `RELATED` edge.

| Query param | Required | Description |
|---|---|---|
| `to_topic_id` | yes | Target topic ID. |
| `kind` | yes | Edge kind string. |

**Response `200`**

```json
{ "ok": "true" }
```

---

## Fields

Fields live inside a topic's `fields_json` blob. Each field has a type, an optional `ref_topic_id`, and an append-only history log.

### `POST /api/ui/topics/{topic_id}/fields`

Appends a new history entry to a field (creates the field if it does not exist).

**Request body**

```json
{
  "field_name": "status",
  "value": "active",
  "field_type": "string",
  "ref_topic_id": null,
  "why_changed": "Initial value",
  "impact_expected": null,
  "provenance": "ui",
  "max_history": 500
}
```

**Response `200`**

```json
{ "version_id": "uuid" }
```

---

### `GET /api/ui/topics/{topic_id}/fields/{field_name}`

Returns a field's current type, reference, and history.

| Query param | Type | Default | Description |
|---|---|---|---|
| `with_history` | `bool` | `true` | Include full history entries. |

**Response `200`**

```json
{
  "field_type": "string",
  "ref_topic_id": null,
  "history": [...]
}
```

---

### `DELETE /api/ui/topics/{topic_id}/fields/{field_name}`

Removes a field and its history from the topic.

**Response `200`**

```json
{ "deleted": "field_name" }
```

---

### `PUT /api/ui/topics/{topic_id}/fields/{field_name}/ref`

Sets or clears the `ref_topic_id` on a field without appending a new history entry.

**Request body**

```json
{ "ref_topic_id": "target-uuid-or-null" }
```

**Response `200`**

```json
{ "ok": "true" }
```

---

### `POST /api/ui/topics/{topic_id}/promote-nested`

Moves a set of fields out of a topic into a new child topic, adds a `RELATED` edge, and optionally creates a back-reference field on the parent.

**Request body**

```json
{
  "field_names": ["field_a", "field_b"],
  "child_title": "Child topic title",
  "child_summary": null,
  "child_topic_id": null,
  "relationship_kind": "has_detail",
  "parent_link_field": null,
  "max_history": 500
}
```

**Response `200`**

```json
{ "ok": true, "child_topic_id": "...", "moved_fields": [...] }
```

---

### `POST /api/ui/topics/{topic_id}/undo-nested`

Reverses a `promote-nested` operation — moves the child's fields back into the parent and removes the edge.

**Request body**

```json
{
  "child_topic_id": "child-uuid",
  "relationship_kind": null
}
```

**Response `200`**

```json
{ "ok": true, ... }
```

---

### `POST /api/ui/topics/{topic_id}/nest-fields`

Groups existing fields under a nested key within `fields_json`.

**Request body**

```json
{
  "field_names": ["field_a", "field_b"],
  "nest_key": "group_name",
  "provenance": "ui"
}
```

**Response `200`**

```json
{ "ok": true, ... }
```

---

### `POST /api/ui/topics/{topic_id}/unnest-fields`

Flattens a nested field group back to the top level.

**Request body**

```json
{ "nest_key": "group_name" }
```

**Response `200`**

```json
{ "ok": true, ... }
```

---

## LLM chat

### `POST /api/llm/chat`

Sends a dialogue to an LLM (Ollama or Groq) with full access to MemState memory tools. The server classifies intent (`query`, `ingest`, or `both`) and selects the appropriate tool set. Long ingest messages automatically use the [Study pipeline](llm-providers.md#study-pipeline).

**Request body**

```json
{
  "messages": [
    { "role": "user", "content": "Remember that the project deadline is June 1." }
  ],
  "provider": "ollama",
  "model": null,
  "ollama_base_url": null,
  "intent_turns": null,
  "intent_override": null,
  "max_tool_rounds": null,
  "study_ingest": true
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `messages` | `list` | required | Chat thread; last message must be `user`. |
| `provider` | `"ollama"` \| `"groq"` | `"ollama"` | LLM provider. |
| `model` | `string \| null` | provider default | Model ID override. |
| `ollama_base_url` | `string \| null` | server default | Ollama base URL override (requires `MEMSTATE_OLLAMA_ALLOW_REMOTE=true` for non-localhost). |
| `intent_turns` | `int \| null` | `MEMSTATE_CHAT_INTENT_TURNS` | Dialogue turns for intent classification (1–64). |
| `intent_override` | `"query" \| "ingest" \| "both" \| null` | — | Skip classification and fix the intent route. |
| `max_tool_rounds` | `int \| null` | `MEMSTATE_CHAT_MAX_TOOL_ROUNDS` | Max tool-call iterations (1–256). |
| `study_ingest` | `bool` | `true` | Use the Study pipeline for long ingest messages. |

**Response `200`**

```json
{
  "reply": "Done. I stored the deadline under...",
  "tool_log": [...],
  "model": "llama3.2:latest",
  "provider": "ollama",
  "intent": "ingest",
  "intent_source": "classifier",
  "max_tool_rounds": 32
}
```

Study responses additionally include `study_ingest`, `study_session_kind`, and `study_phases`.

**Error responses**

| Code | Condition |
|---|---|
| `400` | Invalid request (empty messages, last message not `user`). |
| `502` | Upstream LLM returned an error. |
| `503` | Cannot reach Ollama or Groq (missing key, network error). |

---

## Speech-to-text

### `POST /api/llm/transcribe`
### `POST /api/ui/transcribe`

Both endpoints are identical. Transcribes uploaded audio via Groq Whisper. Requires `GROQ_API_KEY` regardless of chat provider.

**Request** — multipart form upload, field name `audio`. Accepts `webm`, `wav`, `mp3`, `m4a`, and other formats supported by Whisper.

**Response `200`**

```json
{ "text": "Transcribed text here." }
```

See [LLM providers & chat](llm-providers.md) for provider setup.
