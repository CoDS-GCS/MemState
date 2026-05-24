# Configuration

All settings use the `MEMSTATE_` prefix and can be set in `.env` or as environment variables. `GROQ_API_KEY` is the only key loaded *without* the prefix (standard convention).

Copy `.env.example` to `.env` as a starting point.

| Variable | Default | Description |
|---|---|---|
| `MEMSTATE_KUZU_PATH` | `memstate.kuzu` | Path to the embedded Kuzu database file. Parent directories are created automatically. |
| `MEMSTATE_API_KEY` | *(none)* | Bearer / X-API-Key required for all protected endpoints. Leave unset to disable auth. |
| `MEMSTATE_ADMIN_KEY` | *(none)* | Stronger key for protected config updates (e.g. system context). Falls back to `MEMSTATE_API_KEY`. |
| `MEMSTATE_API_HOST` | `0.0.0.0` | Bind address for the HTTP server. |
| `MEMSTATE_API_PORT` | `8765` | Bind port for the HTTP server. |
| `MEMSTATE_OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Ollama API base URL. |
| `MEMSTATE_OLLAMA_MODEL` | `llama3.2:latest` | Default Ollama model for chat. |
| `MEMSTATE_OLLAMA_ALLOW_REMOTE` | `false` | Allow client-supplied Ollama URLs to any host. Disabled by default (SSRF risk). |
| `GROQ_API_KEY` | *(none)* | Groq Cloud API key. Required when `provider=groq`. |
| `MEMSTATE_GROQ_MODEL` | `openai/gpt-oss-20b` | Default Groq model for chat. |
| `MEMSTATE_GROQ_WHISPER_MODEL` | `whisper-large-v3-turbo` | Groq Whisper model for speech-to-text. |
| `MEMSTATE_CHAT_INTENT_TURNS` | `8` | Dialogue turns (1–64) sent to the intent classifier. |
| `MEMSTATE_CHAT_MAX_TOOL_ROUNDS` | `32` | Max LLM↔API tool-call iterations per request (1–256). |
| `MEMSTATE_CHAT_CHUNK_THRESHOLD_CHARS` | `10000` | Character threshold above which the Study pipeline activates for ingest/both intents. |
| `MEMSTATE_CHAT_CHUNK_PER_SEGMENT_TOOL_ROUNDS` | `72` | Tool budget for Study phase A (8–256). |
| `MEMSTATE_STUDY_PHASE_DELAY_SECONDS` | `8.0` | Pause between Study phase A and B to reduce Groq TPM bursts. Set `0` to disable. |
| `MEMSTATE_GROQ_RATE_LIMIT_MAX_RETRIES` | `20` | Max retries on Groq 429 / rate_limit_exceeded (1–100). |
| `MEMSTATE_GROQ_RATE_LIMIT_BACKOFF_CAP_SECONDS` | `120.0` | Cap (seconds) for Groq rate-limit backoff sleep (1–600). |
| `MEMSTATE_QUERY_FIELD_SALIENCE_BUMP` | `0.1` | Salience increase per field read on query intent (0–2). |
| `MEMSTATE_FIELD_SALIENCE_MAX` | `10.0` | Maximum field salience (0.1–10). |

## Further reading

- [Run and configuration (HTML)](../operations/run-config.html) — boot sequence and health checks
