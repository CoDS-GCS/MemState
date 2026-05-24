# Authentication

When `MEMSTATE_API_KEY` is set, all endpoints except `/`, `/health`, `/health/graph`, and `/health/falkordb` require authentication.

Send the key using either:

- `X-API-Key: <key>` header
- `Authorization: Bearer <key>` header

`MEMSTATE_ADMIN_KEY` provides a separate, stronger key for write operations on system configuration (`PUT /api/ui/system-context`). If `MEMSTATE_ADMIN_KEY` is not set, `MEMSTATE_API_KEY` is used for admin checks as well. Send the admin key as `X-Admin-Key`.

## Further reading

- [Configuration](configuration.md) — `MEMSTATE_API_KEY` and `MEMSTATE_ADMIN_KEY`
- [API reference](api-reference.md) — which routes require auth
