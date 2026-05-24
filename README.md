# MemState

**Long-term topic-graph memory for AI agents** — backed by embedded [Kuzu](https://kuzudb.com/), with FastAPI ingest/query, LLM chat (Ollama + Groq), and a D3 graph explorer UI.

**Documentation site:** [github.com/CoDS-GCS/MemState](https://github.com/CoDS-GCS/MemState)

MemState Graph Explorer

## Features

- **Topic graph storage** — versioned fields, salience, embeddings, and typed `RELATED` links
- **Agent API** — `POST /v1/ingest` and `POST /v1/query` for observation-shaped memory operations
- **LLM assistant** — intent-routed chat with memory tools (Ollama or Groq), plus a two-phase Study pipeline for long documents
- **Graph Explorer UI** — visual topic graph, field editing, and built-in assistant panel
- **MCP server** — `memstate-llm-mcp` for Model Context Protocol clients

## Quick start

```bash
pip install -e .
cp .env.example .env
python -m memstate.api.cli   # or: memstate-api
```

Open **[http://127.0.0.1:8765/ui/](http://127.0.0.1:8765/ui/)** for the graph explorer. Interactive API docs: **[http://127.0.0.1:8765/docs](http://127.0.0.1:8765/docs)**


## Documentation

### Repository guides


| Guide                                                | Description                        |
| ---------------------------------------------------- | ---------------------------------- |
| [Quickstart](docs/guides/quickstart.md)              | Install, run, UI controls          |
| [Data model](docs/guides/data-model.md)              | Topics, fields, relationships      |
| [Configuration](docs/guides/configuration.md)        | Environment variables              |
| [API reference](docs/guides/api-reference.md)        | Endpoints, request/response shapes |
| [LLM providers & chat](docs/guides/llm-providers.md) | Ollama, Groq, Study pipeline, MCP  |
| [Authentication](docs/guides/authentication.md)      | API keys and admin access          |
| [Docker](docs/guides/docker.md)                      | Container deployment               |


### Full documentation site

Architecture, operations, and agent integration guides live in `[docs/](docs/index.html)`:


| Section                | Link                                                               |
| ---------------------- | ------------------------------------------------------------------ |
| Product overview       | [docs/index.html](docs/index.html)                                 |
| Developer quickstart   | [docs/developers/quickstart.html](docs/developers/quickstart.html) |
| Architecture           | [docs/architecture/overview.html](docs/architecture/overview.html) |
| Data model (deep dive) | [docs/data-model/overview.html](docs/data-model/overview.html)     |
| Operations             | [docs/operations/high-level.html](docs/operations/high-level.html) |
| HTTP API index         | [docs/api/index.html](docs/api/index.html)                         |


## Requirements

- Python 3.11+
- Optional: [Ollama](https://ollama.com) for local LLM chat, or a [Groq](https://console.groq.com) API key for cloud chat and speech-to-text

## Docker

```bash
docker compose up
```

See [Docker guide](docs/guides/docker.md) for persistence and configuration.

## Project layout

```
src/memstate/     Core library, API, LLM tools, graph store
docs/             Product documentation (HTML) and repository guides (Markdown)
tests/            Pytest suite
```