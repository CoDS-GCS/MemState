"""Thin HTTP SDK for MemState REST API."""

from __future__ import annotations

import os
from typing import Any

import httpx

from memstate.core.models import IngestRequest, IngestResponse, QueryRequest, QueryResponse


class MemoryClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        *,
        timeout: float = 60.0,
    ) -> None:
        self._base = (base_url or os.environ.get("MEMSTATE_API_URL", "http://127.0.0.1:8765")).rstrip(
            "/"
        )
        self._api_key = api_key or os.environ.get("MEMSTATE_API_KEY")
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {}
        if self._api_key:
            h["X-API-Key"] = self._api_key
        return h

    def ingest(self, payload: IngestRequest | dict[str, Any]) -> IngestResponse:
        body = payload if isinstance(payload, IngestRequest) else IngestRequest.model_validate(payload)
        with httpx.Client(timeout=self._timeout) as c:
            r = c.post(
                f"{self._base}/v1/ingest",
                json=body.model_dump(),
                headers=self._headers(),
            )
            r.raise_for_status()
            return IngestResponse.model_validate(r.json())

    def query(self, payload: QueryRequest | dict[str, Any]) -> QueryResponse:
        body = payload if isinstance(payload, QueryRequest) else QueryRequest.model_validate(payload)
        with httpx.Client(timeout=self._timeout) as c:
            r = c.post(
                f"{self._base}/v1/query",
                json=body.model_dump(),
                headers=self._headers(),
            )
            r.raise_for_status()
            return QueryResponse.model_validate(r.json())
