# Docker

```bash
docker compose up
```

The default `docker-compose.yml` builds and starts the API on port `8765`. Mount a volume or set `MEMSTATE_KUZU_PATH` to persist the database outside the container.

The compose file sets `MEMSTATE_KUZU_PATH=/data/memstate.kuzu` and mounts a named volume at `/data`.

## Further reading

- [Configuration](configuration.md) — environment variables
- [Quickstart](quickstart.md) — local (non-Docker) setup
