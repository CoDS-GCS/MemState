from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from memstate.datamodel.fields import TopicFields
from memstate.datamodel.topic import TopicHistoryEvent, TopicNode


def _embedding_from_row(row: dict[str, Any]) -> list[float] | None:
    raw = row.get("embedding")
    if raw is not None:
        if isinstance(raw, (list, tuple)):
            try:
                return [float(x) for x in raw]
            except (TypeError, ValueError):
                pass
    ej = row.get("embedding_json") or ""
    if isinstance(ej, str) and ej.strip():
        try:
            parsed = json.loads(ej)
            if isinstance(parsed, list):
                return [float(x) for x in parsed]
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    return None


def topic_from_graph_row(row: dict[str, Any]) -> TopicNode | None:
    """Map a Cypher RETURN row (flat t.* aliases) to TopicNode."""
    tid = row.get("id")
    if tid is None:
        return None
    hist_raw = row.get("topic_history_json") or "[]"
    history: list[TopicHistoryEvent] = []
    if isinstance(hist_raw, str) and hist_raw.strip():
        try:
            data = json.loads(hist_raw)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        try:
                            history.append(TopicHistoryEvent.model_validate(item))
                        except ValidationError:
                            history.append(
                                TopicHistoryEvent(
                                    ts=str(item.get("ts") or ""),
                                    kind="meta",
                                    detail={"unparsed": item},
                                )
                            )
        except (json.JSONDecodeError, TypeError, ValueError):
            history = []
    tk = row.get("topic_kind")
    fields_raw = row.get("fields_json")
    if isinstance(fields_raw, str):
        fields = TopicFields.from_json(fields_raw)
    else:
        fields = TopicFields()
    return TopicNode(
        id=str(tid),
        title=str(row.get("title") or ""),
        summary=str(row.get("summary") or ""),
        topic_kind=str(tk) if tk is not None and str(tk) != "" else None,
        fields=fields,
        salience=float(row.get("salience") or 0.0),
        failed_salience=float(row.get("failed_salience") or 0.0),
        archived=bool(row.get("archived")),
        created_at=str(row.get("created_at") or ""),
        updated_at=str(row.get("updated_at") or ""),
        history=history,
        embedding=_embedding_from_row(row),
    )


def topic_history_to_json(events: list[TopicHistoryEvent]) -> str:
    return json.dumps([e.model_dump() for e in events], ensure_ascii=False)
