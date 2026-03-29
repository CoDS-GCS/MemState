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

    A topic is the **storage boundary**: one self-contained record (scalars + ``fields_json``)
    with a single embedding. Multiple informal "entities" may be represented inside the same
    topic as field values while they stay small and are not heavily reused across the graph.

    When a piece of meaning grows complex, is associated with many other topics, or needs its
    own revision lifecycle at graph granularity, model it as a **separate** topic and link via
    ``RELATED`` and/or ``ref_topic_id`` on a field.

    Agent-defined fields live in ``fields_json`` (see ``TopicFields``); semantic text uses
    ``embedding`` (vecf32) for similarity.
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
