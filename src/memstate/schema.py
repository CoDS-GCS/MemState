"""
Kuzu embedded graph: Topic uses `fields_json`, optional `topic_kind`, topic_history_json,
failed_salience, DOUBLE[] embedding (+ embedding_json). Topic–topic links use
[:RELATED {kind}]. Legacy FieldHead/FieldVersion may exist; migrate via
`memstate.migrations.migrate_all_legacy_field_chains`.
"""

SCHEMA_VERSION = "3"

# DDL is applied in `memstate.store.kuzu_adapter.bootstrap_kuzu_schema`.
INIT_QUERIES: list[str] = []
INDEX_QUERIES: list[str] = []
VECTOR_INDEX_QUERIES: list[tuple[str, ...] | str] = []


def init_graph(graph) -> None:
    """Create Kuzu node/rel tables and schema meta (idempotent)."""
    from memstate.store.kuzu_adapter import init_kuzu_graph

    init_kuzu_graph(graph)
