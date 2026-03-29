"""REST endpoints for the dev UI: graph snapshot and low-level topic/field/relationship ops."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from memstate.api.deps import get_graph_store
from memstate.api.ui_graph_payload import build_ui_graph_snapshot
from memstate.config import Settings, get_settings
from memstate.llm.groq_transcribe import transcribe_audio_bytes
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


@router.post("/transcribe")
async def transcribe_voice_clip(
    audio: UploadFile = File(..., description="Recorded speech from the UI mic (webm, wav, mp3, m4a, …)"),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    """Same as POST /api/llm/transcribe — lives under /api/ui for the graph UI client."""
    raw = await audio.read()
    text = await transcribe_audio_bytes(
        raw,
        filename=audio.filename or "audio.webm",
        content_type=audio.content_type or "application/octet-stream",
        settings=settings,
    )
    return {"text": text}


@router.get("/graph")
def graph_snapshot(store: GraphStore = Depends(get_graph_store)) -> dict[str, Any]:
    """Return nodes and edges for visualization (topics, RELATED, field refs, ``community`` ids)."""
    return build_ui_graph_snapshot(store)


def _admin_secret(settings: Settings) -> str | None:
    if settings.admin_key and settings.admin_key.strip():
        return settings.admin_key.strip()
    if settings.api_key and settings.api_key.strip():
        return settings.api_key.strip()
    return None


def _is_admin_request(settings: Settings, x_admin_key: str | None) -> bool:
    expected = _admin_secret(settings)
    if not expected:
        return True
    return bool(x_admin_key and x_admin_key.strip() == expected)


class SystemContextBody(BaseModel):
    system_role: str = Field(..., min_length=1, description="Fixed role for the assistant.")
    runtime_context: str = Field(..., min_length=1, description="Runtime environment/context guidance.")


@router.get("/system-context")
def get_system_context(store: GraphStore = Depends(get_graph_store)) -> dict[str, Any]:
    row = store.get_system_config()
    if not row:
        return {"configured": False, "system_context": None}
    return {"configured": True, "system_context": row}


@router.put("/system-context")
def set_system_context(
    body: SystemContextBody,
    store: GraphStore = Depends(get_graph_store),
    settings: Settings = Depends(get_settings),
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
) -> dict[str, Any]:
    configured = store.system_config_exists()
    if configured and not _is_admin_request(settings, x_admin_key):
        raise HTTPException(
            status_code=403,
            detail="Only admin can update system context. Send X-Admin-Key.",
        )
    row = store.set_system_config(
        system_role=body.system_role,
        runtime_context=body.runtime_context,
        updated_by="ui",
    )
    return {"configured": True, "system_context": row}


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
    th_raw = row.get("topic_history_json")
    topic_history: list[Any] = []
    if isinstance(th_raw, str) and th_raw.strip():
        try:
            parsed = json.loads(th_raw)
            if isinstance(parsed, list):
                topic_history = parsed
        except json.JSONDecodeError:
            topic_history = []
    return {
        "id": row.get("id"),
        "title": row.get("title"),
        "summary": row.get("summary"),
        "topic_kind": row.get("topic_kind"),
        "salience": row.get("salience"),
        "failed_salience": row.get("failed_salience"),
        "archived": row.get("archived"),
        "fields": out_fields,
        "topic_history": topic_history,
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


class PromoteNestedTopicBody(BaseModel):
    field_names: list[str]
    child_title: str
    child_summary: str | None = None
    child_topic_id: str | None = None
    relationship_kind: str = "has_detail"
    parent_link_field: str | None = None
    max_history: int = Field(default=500, ge=1, le=10_000)


@router.post("/topics/{topic_id}/promote-nested")
def ui_promote_nested_topic(
    topic_id: str,
    body: PromoteNestedTopicBody,
    store: GraphStore = Depends(get_graph_store),
) -> dict[str, Any]:
    if not store.topic_exists(topic_id):
        raise HTTPException(status_code=404, detail="topic not found")
    try:
        out = store.promote_fields_to_nested_topic(
            topic_id,
            body.field_names,
            body.child_title.strip(),
            child_summary=body.child_summary,
            child_topic_id=body.child_topic_id,
            topic_kind=None,
            relationship_kind=body.relationship_kind,
            parent_link_field=body.parent_link_field,
            link_field_provenance="ui",
            max_history=body.max_history,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, **out}


class NestFieldsInTopicBody(BaseModel):
    field_names: list[str]
    nest_key: str
    provenance: str = "ui"


@router.post("/topics/{topic_id}/nest-fields")
def ui_nest_fields_in_topic(
    topic_id: str,
    body: NestFieldsInTopicBody,
    store: GraphStore = Depends(get_graph_store),
) -> dict[str, Any]:
    if not store.topic_exists(topic_id):
        raise HTTPException(status_code=404, detail="topic not found")
    try:
        out = store.nest_fields_in_topic(
            topic_id,
            body.field_names,
            body.nest_key.strip(),
            provenance=body.provenance,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, **out}


class UnnestFieldsBody(BaseModel):
    nest_key: str


@router.post("/topics/{topic_id}/unnest-fields")
def ui_unnest_fields_in_topic(
    topic_id: str,
    body: UnnestFieldsBody,
    store: GraphStore = Depends(get_graph_store),
) -> dict[str, Any]:
    if not store.topic_exists(topic_id):
        raise HTTPException(status_code=404, detail="topic not found")
    try:
        out = store.unnest_fields_in_topic(topic_id, body.nest_key.strip())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, **out}


class UndoNestedTopicBody(BaseModel):
    child_topic_id: str
    relationship_kind: str | None = None


@router.post("/topics/{topic_id}/undo-nested")
def ui_undo_nested_topic(
    topic_id: str,
    body: UndoNestedTopicBody,
    store: GraphStore = Depends(get_graph_store),
) -> dict[str, Any]:
    if not store.topic_exists(topic_id):
        raise HTTPException(status_code=404, detail="topic not found")
    cid = body.child_topic_id.strip()
    if not cid:
        raise HTTPException(status_code=400, detail="child_topic_id required")
    try:
        out = store.undo_promote_nested_topic(
            topic_id,
            cid,
            relationship_kind=body.relationship_kind,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, **out}
