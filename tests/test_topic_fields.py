"""Unit tests for TopicFields JSON and history capping (no FalkorDB)."""

from __future__ import annotations

import json

from memstate.datamodel.fields import (
    FieldHistoryEntry,
    TopicField,
    TopicFields,
    new_history_entry,
)


def test_topic_fields_roundtrip() -> None:
    tf = TopicFields()
    tf.fields["role"] = TopicField(
        field_type="string",
        ref_topic_id="person-1",
        history=[
            new_history_entry(
                value="lead",
                valid_from="2025-01-01T00:00:00+00:00",
                provenance="test",
                why_changed="promotion",
            )
        ],
    )
    raw = tf.to_json()
    back = TopicFields.from_json(raw)
    assert "role" in back.fields
    assert back.fields["role"].ref_topic_id == "person-1"
    assert back.fields["role"].history[0].value == "lead"
    assert back.fields["role"].history[0].why_changed == "promotion"


def test_cap_history() -> None:
    tf = TopicFields()
    h = [new_history_entry(value=i, valid_from=f"t{i}", provenance="p") for i in range(5)]
    tf.fields["x"] = TopicField(history=h)
    tf.cap_history(3)
    assert len(tf.fields["x"].history) == 3


def test_field_type_coercion() -> None:
    raw = json.dumps(
        {"f": {"field_type": "unknown_type", "history": []}},
        ensure_ascii=False,
    )
    tf = TopicFields.from_json(raw)
    assert tf.fields["f"].field_type == "string"


def test_field_history_entry_extra() -> None:
    e = FieldHistoryEntry.model_validate(
        {"id": "1", "valid_from": "t", "value": "v", "detail": {"x": 1}}
    )
    assert e.value == "v"
