"""REST endpoints for the dev UI: graph snapshot and low-level topic/field/relationship ops."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from memstate.api.deps import get_graph_store
from memstate.api.ui_graph_payload import build_ui_graph_snapshot
from memstate.datamodel.fields import TopicFields, new_history_entry
from memstate.store.graph_store import REF_UNCHANGED, GraphStore

router = APIRouter(prefix="/api/ui", tags=["ui"])

DATAMODEL_MERMAID = """flowchart LR
  subgraph topicA [Topic A]
    metaA[title summary salience topic_kind embedding]
    fieldsA[fields_json]
  end
  subgraph topicB [Topic B]
    metaB[...]
    fieldsB[fields_json]
  end
  topicA -->|RELATED kind| topicB
  fieldsA -->|ref_topic_id on field| topicB
"""


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/datamodel")
def datamodel_diagram() -> dict[str, str]:
    return {"mermaid": DATAMODEL_MERMAID}


@router.get("/graph")
def graph_snapshot(store: GraphStore = Depends(get_graph_store)) -> dict[str, Any]:
    """Return nodes and edges for visualization (topics, RELATED, field refs, ``community`` ids)."""
    return build_ui_graph_snapshot(store)


class CreateTopicBody(BaseModel):
    title: str = "untitled"
    summary: str | None = None
    topic_kind: str | None = None
    salience: float = 1.0
    topic_id: str | None = None


@router.post("/topics")
def ui_create_topic(body: CreateTopicBody, store: GraphStore = Depends(get_graph_store)) -> dict[str, str]:
    tid = body.topic_id or str(uuid.uuid4())
    store.create_topic(
        tid,
        title=body.title,
        summary=body.summary,
        salience=body.salience,
        archived=False,
        embedding=None,
        topic_kind=body.topic_kind,
    )
    return {"topic_id": tid}


@router.get("/topics")
def ui_list_topics(
    store: GraphStore = Depends(get_graph_store),
    include_archived: bool = False,
) -> dict[str, list[str]]:
    return {"topic_ids": store.list_topic_ids(include_archived=include_archived)}


@router.get("/topics/{topic_id}")
def ui_get_topic(topic_id: str, store: GraphStore = Depends(get_graph_store)) -> dict[str, Any]:
    row = store.get_topic(topic_id)
    if not row:
        raise HTTPException(status_code=404, detail="topic not found")
    tf = TopicFields.from_json(row.get("fields_json") if isinstance(row.get("fields_json"), str) else "")
    out_fields: dict[str, Any] = {}
    for name, rec in tf.fields.items():
        out_fields[name] = {
            "field_type": rec.field_type,
            "ref_topic_id": rec.ref_topic_id,
            "history": [e.model_dump() for e in rec.history],
        }
    return {
        "id": row.get("id"),
        "title": row.get("title"),
        "summary": row.get("summary"),
        "topic_kind": row.get("topic_kind"),
        "salience": row.get("salience"),
        "failed_salience": row.get("failed_salience"),
        "archived": row.get("archived"),
        "fields": out_fields,
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


@router.delete("/topics/{topic_id}")
def ui_delete_topic(topic_id: str, store: GraphStore = Depends(get_graph_store)) -> dict[str, Any]:
    if not store.topic_exists(topic_id):
        raise HTTPException(status_code=404, detail="topic not found")
    store.delete_topic(topic_id)
    return {"deleted": topic_id}


class UpdateTopicBody(BaseModel):
    title: str | None = None
    summary: str | None = None
    topic_kind: str | None = None
    salience: float | None = None
    archived: bool | None = None


@router.patch("/topics/{topic_id}")
def ui_update_topic(topic_id: str, body: UpdateTopicBody, store: GraphStore = Depends(get_graph_store)) -> dict[str, str]:
    if not store.topic_exists(topic_id):
        raise HTTPException(status_code=404, detail="topic not found")
    store.update_topic_meta(
        topic_id,
        title=body.title,
        summary=body.summary,
        topic_kind=body.topic_kind,
        salience=body.salience,
        archived=body.archived,
    )
    return {"topic_id": topic_id}


class RelationshipBody(BaseModel):
    to_topic_id: str
    kind: str


@router.post("/topics/{from_id}/relationships")
def ui_add_relationship(
    from_id: str,
    body: RelationshipBody,
    store: GraphStore = Depends(get_graph_store),
) -> dict[str, str]:
    if not store.topic_exists(from_id) or not store.topic_exists(body.to_topic_id):
        raise HTTPException(status_code=404, detail="topic not found")
    store.add_relationship(from_id, body.to_topic_id, body.kind)
    return {"ok": "true"}


@router.delete("/topics/{from_id}/relationships")
def ui_remove_relationship(
    from_id: str,
    to_topic_id: str = Query(...),
    kind: str = Query(...),
    store: GraphStore = Depends(get_graph_store),
) -> dict[str, str]:
    store.remove_relationship(from_id, to_topic_id, kind)
    return {"ok": "true"}


class AppendFieldBody(BaseModel):
    field_name: str
    value: Any = ""
    field_type: str = "string"
    ref_topic_id: str | None = None
    why_changed: str | None = None
    impact_expected: str | None = None
    provenance: str = "ui"
    max_history: int = Field(default=500, ge=1, le=10_000)


@router.post("/topics/{topic_id}/fields")
def ui_append_field(
    topic_id: str,
    body: AppendFieldBody,
    store: GraphStore = Depends(get_graph_store),
) -> dict[str, str]:
    if not store.topic_exists(topic_id):
        raise HTTPException(status_code=404, detail="topic not found")
    entry = new_history_entry(
        value=body.value,
        valid_from=_utc_iso(),
        provenance=body.provenance,
        why_changed=body.why_changed,
        impact_expected=body.impact_expected,
    )
    ref_kw = REF_UNCHANGED if body.ref_topic_id is None else body.ref_topic_id
    vid = store.append_field_history(
        topic_id,
        body.field_name,
        entry,
        field_type=body.field_type,
        ref_topic_id=ref_kw,
        max_history=body.max_history,
    )
    return {"version_id": vid}


@router.get("/topics/{topic_id}/fields/{field_name}")
def ui_get_field(
    topic_id: str,
    field_name: str,
    store: GraphStore = Depends(get_graph_store),
    with_history: bool = True,
) -> dict[str, Any]:
    if with_history:
        tf = store.get_field_with_history(topic_id, field_name)
    else:
        tf = store.get_field(topic_id, field_name)
    if not tf:
        raise HTTPException(status_code=404, detail="field not found")
    return {
        "field_type": tf.field_type,
        "ref_topic_id": tf.ref_topic_id,
        "history": [e.model_dump() for e in tf.history],
    }


@router.delete("/topics/{topic_id}/fields/{field_name}")
def ui_delete_field(topic_id: str, field_name: str, store: GraphStore = Depends(get_graph_store)) -> dict[str, str]:
    store.delete_field(topic_id, field_name)
    return {"deleted": field_name}


class SetFieldRefBody(BaseModel):
    ref_topic_id: str | None = None


@router.put("/topics/{topic_id}/fields/{field_name}/ref")
def ui_set_field_ref(
    topic_id: str,
    field_name: str,
    body: SetFieldRefBody,
    store: GraphStore = Depends(get_graph_store),
) -> dict[str, str]:
    store.set_field_ref(topic_id, field_name, body.ref_topic_id)
    return {"ok": "true"}
