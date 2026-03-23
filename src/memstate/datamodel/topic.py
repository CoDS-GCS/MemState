from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from memstate.datamodel.fields import TopicFields


class TopicHistoryEvent(BaseModel):
    """Append-only topic-level audit trail stored in `topic_history_json` on :Topic."""

    model_config = ConfigDict(extra="ignore")

    ts: str = ""
    kind: Literal["created", "salience", "meta", "embedding", "failed_signal"] = "meta"
    detail: dict[str, Any] = Field(default_factory=dict)


class TopicNode(BaseModel):
    """
    Logical :Topic node in the graph store.

    Agent-defined fields live in `fields_json` on the node (see `TopicFields`);
    semantic text uses `embedding` (vecf32) for similarity.
    """

    id: str
    title: str = ""
    summary: str = ""
    topic_kind: str | None = None
    fields: TopicFields = Field(default_factory=TopicFields)
    salience: float = 1.0
    failed_salience: float = 0.0
    archived: bool = False
    created_at: str = ""
    updated_at: str = ""
    history: list[TopicHistoryEvent] = Field(default_factory=list)
    embedding: list[float] | None = None
