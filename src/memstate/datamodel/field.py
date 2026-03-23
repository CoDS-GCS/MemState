from __future__ import annotations

from pydantic import BaseModel, Field


class FieldHeadNode(BaseModel):
    """Deprecated: legacy (:FieldHead) — prefer `fields_json` on :Topic."""

    topic_id: str
    field_name: str


class FieldVersionNode(BaseModel):
    """Deprecated: legacy (:FieldVersion)."""

    id: str
    value: str = ""
    valid_from: str = ""
    provenance: str = ""


class FieldWithHistory(BaseModel):
    """Convenience bundle: legacy graph chain or name + TopicField in API layer."""

    name: str
    current: FieldVersionNode | None = None
    history: list[FieldVersionNode] = Field(default_factory=list)
