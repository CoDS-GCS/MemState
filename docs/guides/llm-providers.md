# LLM providers, chat, and MCP

## Ollama (default)

Runs locally. [Install Ollama](https://ollama.com), then:

```bash
ollama pull llama3.2      # recommended for tool use
ollama serve              # starts on :11434
```

Set `MEMSTATE_OLLAMA_MODEL` to switch models. Tool-capable models work best (e.g. `llama3.2`, `qwen2.5`, `mistral`).

## Groq

Set `GROQ_API_KEY` in `.env`. Groq is invoked when `provider=groq` is passed to `/api/llm/chat`. The default model is `openai/gpt-oss-20b`; override with `MEMSTATE_GROQ_MODEL`.

Groq rate limits are handled automatically with configurable backoff retries (`MEMSTATE_GROQ_RATE_LIMIT_MAX_RETRIES`, `MEMSTATE_GROQ_RATE_LIMIT_BACKOFF_CAP_SECONDS`).

## Study pipeline

When a chat message's last user turn exceeds `MEMSTATE_CHAT_CHUNK_THRESHOLD_CHARS` characters and the intent is `ingest` or `both`, MemState runs a two-phase Study pipeline instead of a single LLM call:

1. **Phase A — sandbox:** builds a structural hierarchy of the document, then runs an ingest pass using a `study:<session_id>` topic kind. All new topics are scoped to the session.
2. **Phase B — integrate:** links Study topics into the existing memory graph, merges duplicates, and updates `topic_kind` when appropriate.

A configurable delay (`MEMSTATE_STUDY_PHASE_DELAY_SECONDS`) between phases reduces Groq TPM bursts. Set `study_ingest=false` in the request body to force a single-call flow.

See [Configuration](configuration.md) for Study-related tuning variables.

## Speech-to-text

Both `POST /api/llm/transcribe` and `POST /api/ui/transcribe` transcribe uploaded audio via Groq Whisper. Requires `GROQ_API_KEY` regardless of chat provider.

Request: multipart form upload, field name `audio`. Accepts `webm`, `wav`, `mp3`, `m4a`, and other formats supported by Whisper.

Response `200`:

```json
{ "text": "Transcribed text here." }
```

## MCP server

MemState exposes an MCP (Model Context Protocol) server for integration with MCP-compatible clients:

```bash
memstate-llm-mcp
```

## Further reading

- [API reference — LLM chat](api-reference.md#llm-chat) — `POST /api/llm/chat` request/response
- [HTTP stack (HTML)](../architecture/http-stack.html) — routers and LLM integration
