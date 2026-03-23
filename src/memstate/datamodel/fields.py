"""Typed topic fields with value-only history and optional field-level ref_topic_id."""

from __future__ import annotations

import json
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

FieldType = Literal["string", "int", "float", "bool", "date", "datetime", "list", "json"]

_ALLOWED_TYPES = frozenset(
    ("string", "int", "float", "bool", "date", "datetime", "list", "json")
)


class FieldHistoryEntry(BaseModel):
    """One value revision; newest-first when stored in `TopicField.history`."""

    model_config = ConfigDict(extra="allow")

    id: str = ""
    valid_from: str = ""
    value: Any = None
    why_changed: str | None = None
    impact_expected: str | None = None
    provenance: str = "api"


class TopicField(BaseModel):
    """Field record: type, optional expand ref, ordered history (newest first)."""

    model_config = ConfigDict(extra="ignore")

    field_type: FieldType = "string"
    ref_topic_id: str | None = None
    history: list[FieldHistoryEntry] = Field(default_factory=list)
    salience: float = Field(
        default=1.0,
        ge=0.0,
        le=10.0,
        description="Per-field salience (0–10). Topic salience is the average of its fields.",
    )

    @field_validator("field_type", mode="before")
    @classmethod
    def _coerce_field_type(cls, v: Any) -> str:
        s = str(v) if v is not None else "string"
        return s if s in _ALLOWED_TYPES else "string"

    @field_validator("salience", mode="before")
    @classmethod
    def _clamp_salience(cls, v: Any) -> float:
        try:
            x = float(v)
        except (TypeError, ValueError):
            return 1.0
        return max(0.0, min(10.0, x))

    def current_entry(self) -> FieldHistoryEntry | None:
        return self.history[0] if self.history else None


def new_history_entry(
    *,
    value: Any,
    valid_from: str,
    provenance: str = "api",
    why_changed: str | None = None,
    impact_expected: str | None = None,
) -> FieldHistoryEntry:
    return FieldHistoryEntry(
        id=str(uuid.uuid4()),
        valid_from=valid_from,
        value=value,
        why_changed=why_changed,
        impact_expected=impact_expected,
        provenance=provenance,
    )


class TopicFields(BaseModel):
    """Map field name -> TopicField."""

    model_config = ConfigDict(extra="ignore")

    fields: dict[str, TopicField] = Field(default_factory=dict)

    @classmethod
    def from_json(cls, raw: str | None) -> TopicFields:
        if not raw or not str(raw).strip():
            return cls()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return cls()
        if not isinstance(data, dict):
            return cls()
        out: dict[str, TopicField] = {}
        for name, payload in data.items():
            if not isinstance(name, str) or not isinstance(payload, dict):
                continue
            try:
                out[name] = TopicField.model_validate(payload)
            except Exception:
                continue
        return cls(fields=out)

    def to_json(self) -> str:
        return json.dumps(
            {k: v.model_dump() for k, v in self.fields.items()},
            ensure_ascii=False,
        )

    def cap_history(self, max_entries: int) -> None:
        if max_entries <= 0:
            return
        for tf in self.fields.values():
            if len(tf.history) > max_entries:
                tf.history = tf.history[:max_entries]
