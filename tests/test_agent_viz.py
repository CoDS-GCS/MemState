"""Tests for agent visualization hint mapping."""

from memstate.llm.agent_viz import build_viz_hint


def test_scan_list_topics():
    viz = build_viz_hint(
        "memory_list_topics",
        {"include_archived": False},
        {"ok": True, "topic_ids": ["a", "b", "c"], "topics": []},
    )
    assert viz["action"] == "scan"
    assert viz["viz_focus"] == "scan"
    assert viz["topic_ids"] == ["a", "b", "c"]
    assert "3 topics" in viz["label"]


def test_read_topic_schema():
    tid = "11111111-1111-4111-8111-111111111111"
    viz = build_viz_hint(
        "memory_get_topic_schema",
        {"topic_id": tid, "detail": "minimal"},
        {"ok": True, "topic_id": tid, "fields": {}},
    )
    assert viz["action"] == "read"
    assert viz["viz_focus"] == "topic"
    assert viz["field_target"] is None
    assert viz["topic_ids"] == [tid]


def test_read_field():
    tid = "11111111-1111-4111-8111-111111111111"
    viz = build_viz_hint(
        "memory_get_field",
        {"topic_id": tid, "field_name": "married"},
        {"ok": True, "field": {"field_type": "string", "history": [{"value": "yes"}]}},
    )
    assert viz["viz_focus"] == "field"
    assert viz["field_target"] == {"name": "married"}
    assert viz["topic_ids"] == [tid]
    assert "married" in viz["label"]


def test_read_nested_inner_field():
    tid = "11111111-1111-4111-8111-111111111111"
    viz = build_viz_hint(
        "memory_get_field",
        {"topic_id": tid, "field_name": "employment", "nested_field_name": "company"},
        {"ok": True, "nest_key": "employment", "nested_field_name": "company", "field": {}},
    )
    assert viz["viz_focus"] == "field"
    assert viz["field_target"] == {"name": "company", "nest_key": "employment"}
    assert "company" in viz["label"]
    assert "employment" in viz["label"]


def test_read_nested_auto_resolved():
    tid = "11111111-1111-4111-8111-111111111111"
    viz = build_viz_hint(
        "memory_get_field",
        {"topic_id": tid, "field_name": "married"},
        {"ok": True, "nest_key": "personal_life", "nested_field_name": "married", "field": {}},
    )
    assert viz["viz_focus"] == "field"
    assert viz["field_target"] == {"name": "married", "nest_key": "personal_life"}


def test_read_nested_bundle_outer_only():
    tid = "11111111-1111-4111-8111-111111111111"
    bundle_val = {"_memstate_nested": True, "fields": {"company": {"field_type": "string"}}}
    viz = build_viz_hint(
        "memory_get_field",
        {"topic_id": tid, "field_name": "employment"},
        {
            "ok": True,
            "field": {
                "field_type": "json",
                "history": [{"value": bundle_val}],
            },
        },
    )
    assert viz["viz_focus"] == "field"
    assert viz["field_target"] is None
    assert viz["field_names"] == ["company"]
    assert viz["nest_key"] == "employment"
    assert viz["highlight_fields"] is True
    assert "employment" in viz["label"]


def test_read_nested_bundle_personal_life():
    tid = "11111111-1111-4111-8111-111111111111"
    inner_keys = [
        "birth_city",
        "birth_country",
        "birth_place",
        "marriage_date",
        "married",
        "resident_country",
        "wife_name",
        "work_permit_valid_until",
    ]
    bundle_val = {
        "_memstate_nested": True,
        "fields": {k: {"field_type": "string"} for k in inner_keys},
    }
    viz = build_viz_hint(
        "memory_get_field",
        {"topic_id": tid, "field_name": "personal_life"},
        {
            "ok": True,
            "field": {
                "field_type": "json",
                "history": [{"value": bundle_val}],
            },
        },
    )
    assert viz["viz_focus"] == "field"
    assert viz["field_names"] == sorted(inner_keys)
    assert viz["nest_key"] == "personal_life"
    assert viz["highlight_fields"] is True
    assert "8 fields" in viz["label"]


def test_write_field():
    tid = "22222222-2222-4222-8222-222222222222"
    viz = build_viz_hint(
        "memory_append_field",
        {"topic_id": tid, "field_name": "birth_place", "value": "Cairo"},
        {"ok": True, "version_id": "v1"},
    )
    assert viz["action"] == "write_field"
    assert viz["viz_focus"] == "field"
    assert viz["field_target"] == {"name": "birth_place"}
    assert viz["topic_ids"] == [tid]


def test_write_edge():
    a = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    b = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    viz = build_viz_hint(
        "memory_add_relationship",
        {"from_topic_id": a, "to_topic_id": b, "kind": "associated_with"},
        {"ok": True},
    )
    assert viz["action"] == "write_edge"
    assert viz["viz_focus"] == "topic"
    assert set(viz["topic_ids"]) == {a, b}
    assert viz["edge"] == {
        "from_topic_id": a,
        "to_topic_id": b,
        "kind": "associated_with",
    }


def test_read_topic_schema_fields_from_result():
    tid = "11111111-1111-4111-8111-111111111111"
    viz_min = build_viz_hint(
        "memory_get_topic_schema",
        {"topic_id": tid, "detail": "minimal"},
        {
            "ok": True,
            "topic_id": tid,
            "fields": {"married": {"field_type": "string"}, "birth_place": {"field_type": "string"}},
        },
    )
    assert viz_min["viz_focus"] == "topic"
    assert viz_min["field_target"] is None

    viz_cur = build_viz_hint(
        "memory_get_topic_schema",
        {"topic_id": tid, "detail": "current"},
        {
            "ok": True,
            "topic_id": tid,
            "fields": {
                "married": {"field_type": "string", "value": "yes"},
                "birth_place": {"field_type": "string", "value": "Cairo"},
            },
        },
    )
    assert viz_cur["viz_focus"] == "topic"
    assert viz_cur["field_target"] is None


def test_read_full_topic_fields_from_result():
    tid = "11111111-1111-4111-8111-111111111111"
    viz = build_viz_hint(
        "memory_get_topic",
        {"topic_id": tid},
        {
            "ok": True,
            "topic": {
                "id": tid,
                "fields": {"status": {}, "role": {}},
            },
        },
    )
    assert viz["viz_focus"] == "topic"
    assert viz["field_target"] is None


def test_create_topic():
    viz = build_viz_hint(
        "memory_create_topic",
        {"title": "Alice", "summary": "Person"},
        {"ok": True, "topic_id": "cccccccc-cccc-4ccc-8ccc-cccccccccccc"},
    )
    assert viz["action"] == "write_topic"
    assert viz["viz_focus"] == "topic"
    assert viz["topic_ids"] == ["cccccccc-cccc-4ccc-8ccc-cccccccccccc"]
    assert "Alice" in viz["label"]
