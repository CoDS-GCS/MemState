"""Embedded Kuzu graph: same Cypher façade as FalkorDB (`query` / `ro_query` + result shape)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import kuzu

from memstate.config import Settings, get_settings
from memstate.schema import SCHEMA_VERSION


def _adapt_result(kr: kuzu.QueryResult) -> SimpleNamespace:
    cols = kr.get_column_names()
    header: list[tuple[str, ...]] = [(c,) for c in cols]
    rows: list[list[Any]] = []
    while kr.has_next():
        row = kr.get_next()
        rows.append(list(row) if isinstance(row, (list, tuple)) else [row])
    return SimpleNamespace(header=header, result_set=rows)


def _ignore_exists(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "already exists" in msg or "duplicate" in msg


def bootstrap_kuzu_schema(conn: kuzu.Connection) -> None:
    """Create node/rel tables once (idempotent)."""
    stmts = [
        """
        CREATE NODE TABLE MemStateMeta(
            key STRING,
            version STRING,
            PRIMARY KEY (key)
        )
        """,
        """
        CREATE NODE TABLE SystemConfig(
            key STRING,
            system_role STRING,
            runtime_context STRING,
            created_at STRING,
            updated_at STRING,
            updated_by STRING,
            PRIMARY KEY (key)
        )
        """,
        """
        CREATE NODE TABLE Topic(
            id STRING,
            title STRING,
            summary STRING,
            topic_kind STRING,
            salience DOUBLE,
            failed_salience DOUBLE,
            created_at STRING,
            updated_at STRING,
            archived BOOLEAN,
            topic_history_json STRING,
            fields_json STRING,
            embedding DOUBLE[],
            embedding_json STRING,
            PRIMARY KEY (id)
        )
        """,
        """
        CREATE NODE TABLE FieldHead(
            id STRING,
            topic_id STRING,
            field_name STRING,
            PRIMARY KEY (id)
        )
        """,
        """
        CREATE NODE TABLE FieldVersion(
            id STRING,
            value STRING,
            valid_from STRING,
            provenance STRING,
            PRIMARY KEY (id)
        )
        """,
        "CREATE REL TABLE RELATED(FROM Topic TO Topic, kind STRING)",
        "CREATE REL TABLE HAS_FIELD(FROM Topic TO FieldHead, name STRING)",
        "CREATE REL TABLE LATEST(FROM FieldHead TO FieldVersion)",
        "CREATE REL TABLE PREV(FROM FieldVersion TO FieldVersion)",
    ]
    for q in stmts:
        try:
            conn.execute(q)
        except Exception as e:
            if not _ignore_exists(e):
                raise
    conn.execute(
        "MERGE (m:MemStateMeta {key: $k}) ON CREATE SET m.version = $v ON MATCH SET m.version = $v",
        {"k": "schema", "v": SCHEMA_VERSION},
    )


class KuzuGraph:
    """Minimal graph handle expected by `GraphStore` and `init_graph`."""

    __slots__ = ("_db", "_conn", "db_path")

    def __init__(self, resolved_path: str) -> None:
        """Open DB at *resolved_path* (absolute, normalized). One process may hold one handle per file."""
        self.db_path = resolved_path
        self._db = kuzu.Database(self.db_path)
        self._conn = kuzu.Connection(self._db)

    def query(self, cypher: str, params: dict[str, Any] | None = None) -> SimpleNamespace:
        res = self._conn.execute(cypher, params or {})
        if isinstance(res, list):
            res = res[-1]
        return _adapt_result(res)

    def ro_query(self, cypher: str, params: dict[str, Any] | None = None) -> SimpleNamespace:
        return self.query(cypher, params)

    @property
    def connection(self) -> kuzu.Connection:
        return self._conn


@lru_cache(maxsize=32)
def _open_kuzu_at(resolved_path: str) -> KuzuGraph:
    """Single `KuzuGraph` per resolved file path — Kuzu allows only one writer per database file."""
    Path(resolved_path).parent.mkdir(parents=True, exist_ok=True)
    return KuzuGraph(resolved_path)


def clear_kuzu_graph_cache() -> None:
    """Tests / hot-reload: drop cached handles before opening a different path."""
    _open_kuzu_at.cache_clear()


def get_kuzu_graph(settings: Settings | None = None) -> KuzuGraph:
    s = settings or get_settings()
    p = str(Path(s.kuzu_path).expanduser().resolve())
    return _open_kuzu_at(p)


def init_kuzu_graph(graph: KuzuGraph) -> None:
    bootstrap_kuzu_schema(graph.connection)
