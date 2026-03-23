"""One-time migration helpers (legacy FieldHead/FieldVersion → fields_json)."""

from __future__ import annotations

from memstate.store.graph_store import GraphStore


def migrate_all_legacy_field_chains(store: GraphStore) -> int:
    """Run `migrate_legacy_field_chains_to_json` for every topic. Returns total fields migrated."""
    total = 0
    for tid in store.list_topic_ids(include_archived=True):
        total += store.migrate_legacy_field_chains_to_json(tid)
    return total
