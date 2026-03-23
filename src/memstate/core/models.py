from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Policies(BaseModel):
    """P_t — tunable governance (subset for v1)."""

    max_field_history: int = 500
    max_topics_for_forget_scan: int = 10_000
    forget_salience_threshold: float = 0.05
    """Topics below this salience may be archived by forget."""

    topic_count_soft_limit: int = 500
    """When topic count exceeds this, reasoner may run forget more aggressively."""
    query_salience_bump: float = 0.1
    embedding_dimension: int = 384


class FieldWrite(BaseModel):
    name: str
    value: Any = ""
    field_type: str = "string"
    ref_topic_id: str | None = None
    why_changed: str | None = None
    impact_expected: str | None = None
    provenance: str = "api"


class EdgeWrite(BaseModel):
    to_topic_id: str
    kind: str


Placement = Literal["new_topic", "extend_topic", "version_field"]


class IngestRequest(BaseModel):
    placement: Placement
    """new_topic: create topic + optional fields. extend_topic: add fields to topic_id. version_field: append to field history."""

    topic_id: str | None = None
    title: str = ""
    summary: str | None = None
    topic_kind: str | None = None
    salience: float = 1.0
    fields: list[FieldWrite] = Field(default_factory=list)
    edges: list[EdgeWrite] = Field(default_factory=list)
    suggest_similar: bool = False
    """If true, response includes vector top-k topic ids (hints only)."""


class IngestResponse(BaseModel):
    topic_id: str
    applied: list[str] = Field(default_factory=list)
    version_ids: dict[str, str] = Field(default_factory=dict)
    similar_topic_ids: list[str] = Field(default_factory=list)


class QueryRequest(BaseModel):
    q: str
    stages: list[Literal["semantic", "structural", "temporal"]] = Field(
        default_factory=lambda: ["semantic", "structural", "temporal"]
    )
    explain: bool = False
    top_k: int = 8
    topic_ids: list[str] | None = None
    field_names: list[str] | None = None


class FieldVersionOut(BaseModel):
    id: str
    value: Any = None
    valid_from: str | None = None
    provenance: str | None = None
    why_changed: str | None = None
    impact_expected: str | None = None


class FieldOut(BaseModel):
    name: str
    field_type: str | None = None
    ref_topic_id: str | None = None
    current: FieldVersionOut | None = None
    history: list[FieldVersionOut] = Field(default_factory=list)


class TopicBundle(BaseModel):
    topic_id: str
    title: str | None = None
    summary: str | None = None
    topic_kind: str | None = None
    salience: float | None = None
    failed_salience: float | None = None
    neighbors: list[dict[str, Any]] = Field(default_factory=list)
    fields: list[FieldOut] = Field(default_factory=list)
    similarity: float | None = None


class QueryResponse(BaseModel):
    query: str
    candidates: list[TopicBundle] = Field(default_factory=list)
    summary_text: str = ""


class IngestProcessor(BaseModel):
    """Placeholder for future LLM ingest processor (v1: unused)."""

    model_config = {"extra": "allow"}


class QueryProcessor(BaseModel):
    """Placeholder for future LLM query processor (v1: unused)."""

    model_config = {"extra": "allow"}
