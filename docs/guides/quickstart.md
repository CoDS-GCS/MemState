# Quickstart

## Install and run

```bash
pip install -e .
cp .env.example .env        # edit as needed
python -m memstate.api.cli  # or: memstate-api
```

Open `http://127.0.0.1:8765/ui/` for the graph explorer.

Interactive API docs are available at `http://127.0.0.1:8765/docs`.

## Graph Explorer UI

The **MemState Graph Explorer** (served with the API) shows topics as cards on a canvas, **RELATED** edges vs **field ref** edges, and side rails for graph edits plus the assistant (provider/model, chat).

![MemState Graph Explorer](../images/graph-explorer-ui.png)

**Controls:** scroll to zoom · drag background to pan · drag nodes to rearrange · double-click empty SVG to reset zoom.

## OneDrive / cloud-sync warning

Kuzu holds an exclusive file lock. Set `MEMSTATE_KUZU_PATH` to a path outside any synced folder (e.g. `%LOCALAPPDATA%\MemState\memstate.kuzu` on Windows) to avoid lock conflicts.

## Next steps

- [Configuration](configuration.md) — environment variables
- [API reference](api-reference.md) — HTTP endpoints
- [Developer quickstart (HTML)](../developers/quickstart.html) — agent integration with `/v1/ingest` and `/v1/query`
