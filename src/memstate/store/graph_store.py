from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import numpy as np

from memstate.config import Settings, get_settings
from memstate.store.kuzu_adapter import KuzuGraph, get_kuzu_graph
from memstate.datamodel.fields import (
    FieldHistoryEntry,
    TopicField,
    TopicFields,
    new_history_entry,
)
from memstate.schema import init_graph

_UNSET = object()

# Pass `REF_UNCHANGED` as `ref_topic_id` to append/update when the ref should stay as-is.
REF_UNCHANGED = _UNSET


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _col_names(result) -> list[str]:
    h = result.header
    out: list[str] = []
    for item in h:
        if isinstance(item, (list, tuple)) and len(item) >= 1:
            out.append(str(item[0]))
        else:
            out.append(str(item))
    return out


def _row1(result) -> dict[str, Any] | None:
    rows = result.result_set
    if not rows:
        return None
    header = _col_names(result)
    return dict(zip(header, rows[0]))


def _rows(result) -> list[dict[str, Any]]:
    if not result.header:
        return []
    header = _col_names(result)
    return [dict(zip(header, row)) for row in result.result_set]


class GraphStore:
    """Block 1 façade — Kuzu Cypher (embedded)."""

    def __init__(self, graph) -> None:
        self._g = graph

    @property
    def graph(self):
        return self._g

    def init_schema(self) -> None:
        init_graph(self._g)

    def _q(self, cypher: str, params: dict[str, Any] | None = None, *, read_only: bool = False):
        if read_only:
            return self._g.ro_query(cypher, params)
        return self._g.query(cypher, params)

    def topic_exists(self, topic_id: str) -> bool:
        r = self._q(
            "MATCH (t:Topic {id: $id}) RETURN count(t) AS c",
            {"id": topic_id},
            read_only=True,
        )
        row = _row1(r)
        return bool(row and row.get("c", 0) >= 1)

    def get_topic(self, topic_id: str) -> dict[str, Any] | None:
        r = self._q(
            """
            MATCH (t:Topic {id: $id})
            RETURN t.id AS id, t.title AS title, t.summary AS summary,
                   t.topic_kind AS topic_kind,
                   t.salience AS salience, t.failed_salience AS failed_salience,
                   t.archived AS archived,
                   t.topic_history_json AS topic_history_json,
                   t.fields_json AS fields_json,
                   t.embedding AS embedding, t.embedding_json AS embedding_json,
                   t.created_at AS created_at, t.updated_at AS updated_at
            """,
            {"id": topic_id},
            read_only=True,
        )
        return _row1(r)

    def _get_topic_fields(self, topic_id: str) -> TopicFields:
        row = self.get_topic(topic_id)
        if not row:
            return TopicFields()
        raw = row.get("fields_json")
        return TopicFields.from_json(raw) if isinstance(raw, str) else TopicFields()

    def _set_topic_fields(self, topic_id: str, tf: TopicFields) -> None:
        self._q(
            """
            MATCH (t:Topic {id: $id})
            SET t.fields_json = $fj, t.updated_at = $updated_at
            """,
            {"id": topic_id, "fj": tf.to_json(), "updated_at": _now_iso()},
        )

    @staticmethod
    def average_field_salience(tf: TopicFields) -> float:
        if not tf.fields:
            return 1.0
        vals = [float(f.salience) for f in tf.fields.values()]
        return sum(vals) / len(vals)

    def bump_field_salience_on_query(
        self,
        topic_id: str,
        field_names: list[str],
        *,
        bump: float,
        max_field_salience: float,
    ) -> None:
        """Increase salience on named fields (capped); set topic salience to the average of field saliences."""
        if not field_names or bump <= 0:
            return
        tf = self._get_topic_fields(topic_id)
        if not tf.fields:
            return
        for name in field_names:
            if name not in tf.fields:
                continue
            rec = tf.fields[name]
            rec.salience = min(max_field_salience, float(rec.salience) + bump)
        avg = self.average_field_salience(tf)
        self._set_topic_fields(topic_id, tf)
        self.update_topic_meta(topic_id, salience=avg)

    def sync_topic_salience_from_fields(self, topic_id: str) -> None:
        """Set topic ``salience`` to the average of all field saliences."""
        tf = self._get_topic_fields(topic_id)
        avg = self.average_field_salience(tf)
        self.update_topic_meta(topic_id, salience=avg)

    def create_topic(
        self,
        topic_id: str,
        title: str,
        summary: str | None,
        salience: float,
        archived: bool,
        embedding: list[float] | None,
        *,
        failed_salience: float = 0.0,
        topic_kind: str | None = None,
        initial_fields: TopicFields | None = None,
    ) -> None:
        ts = _now_iso()
        topic_history_json = json.dumps(
            [{"ts": ts, "kind": "created", "detail": {"title": title}}],
            ensure_ascii=False,
        )
        tf = initial_fields or TopicFields()
        emb_list: list[float] = [float(x) for x in embedding] if embedding else []
        self._q(
            """
            CREATE (t:Topic {
              id: $id,
              title: $title,
              summary: $summary,
              topic_kind: $topic_kind,
              salience: $salience,
              failed_salience: $failed_salience,
              created_at: $created_at,
              updated_at: $updated_at,
              archived: $archived,
              topic_history_json: $topic_history_json,
              fields_json: $fields_json,
              embedding: $embedding,
              embedding_json: $embedding_json
            })
            """,
            {
                "id": topic_id,
                "title": title,
                "summary": summary or "",
                "topic_kind": topic_kind or "",
                "salience": salience,
                "failed_salience": failed_salience,
                "created_at": ts,
                "updated_at": ts,
                "archived": archived,
                "topic_history_json": topic_history_json,
                "fields_json": tf.to_json(),
                "embedding": emb_list,
                "embedding_json": json.dumps(embedding) if embedding else "",
            },
        )

    def update_topic_embedding(self, topic_id: str, embedding: list[float]) -> None:
        u = _now_iso()
        ej = json.dumps(embedding)
        emb_list = [float(x) for x in embedding]
        self._q(
            """
            MATCH (t:Topic {id: $id})
            SET t.embedding = $emb,
                t.embedding_json = $embedding_json,
                t.updated_at = $updated_at
            """,
            {"id": topic_id, "emb": emb_list, "embedding_json": ej, "updated_at": u},
        )

    def update_topic_meta(
        self,
        topic_id: str,
        *,
        title: str | None = None,
        summary: str | None = None,
        topic_kind: str | None = None,
        salience: float | None = None,
        failed_salience: float | None = None,
        archived: bool | None = None,
    ) -> None:
        sets = ["t.updated_at = $updated_at"]
        params: dict[str, Any] = {"id": topic_id, "updated_at": _now_iso()}
        if title is not None:
            sets.append("t.title = $title")
            params["title"] = title
        if summary is not None:
            sets.append("t.summary = $summary")
            params["summary"] = summary
        if topic_kind is not None:
            sets.append("t.topic_kind = $topic_kind")
            params["topic_kind"] = topic_kind
        if salience is not None:
            sets.append("t.salience = $salience")
            params["salience"] = salience
        if failed_salience is not None:
            sets.append("t.failed_salience = $failed_salience")
            params["failed_salience"] = failed_salience
        if archived is not None:
            sets.append("t.archived = $archived")
            params["archived"] = archived
        q = f"MATCH (t:Topic {{id: $id}}) SET {', '.join(sets)}"
        self._q(q, params)

    def append_topic_history(self, topic_id: str, event: dict[str, Any]) -> None:
        r = self._q(
            "MATCH (t:Topic {id: $id}) RETURN coalesce(t.topic_history_json, '[]') AS h",
            {"id": topic_id},
            read_only=True,
        )
        row = _row1(r)
        if not row:
            return
        raw = row.get("h") or "[]"
        try:
            arr = json.loads(raw) if isinstance(raw, str) else []
        except json.JSONDecodeError:
            arr = []
        if not isinstance(arr, list):
            arr = []
        arr.append(event)
        self._q(
            """
            MATCH (t:Topic {id: $id})
            SET t.topic_history_json = $hj, t.updated_at = $updated_at
            """,
            {"id": topic_id, "hj": json.dumps(arr, ensure_ascii=False), "updated_at": _now_iso()},
        )

    def vector_knn_topic_ids(self, query_embedding: list[float], k: int) -> list[tuple[str, float]]:
        if k <= 0 or not query_embedding:
            return []
        return self._vector_knn_numpy(query_embedding, k)

    def _vector_knn_numpy(self, query_embedding: list[float], k: int) -> list[tuple[str, float]]:
        q = np.array(query_embedding, dtype=float)
        qn = float(np.linalg.norm(q)) or 1.0
        rows = self.list_topics_for_embedding_scan(include_archived=False)
        scored: list[tuple[str, float]] = []
        for row in rows:
            emb = row.get("embedding")
            if isinstance(emb, (list, tuple)) and emb and isinstance(emb[0], (list, tuple)):
                emb = emb[0]
            if not emb:
                ej = row.get("embedding_json")
                if not ej:
                    continue
                try:
                    emb = json.loads(ej) if isinstance(ej, str) else None
                except json.JSONDecodeError:
                    continue
            if not emb:
                continue
            v = np.array(emb, dtype=float)
            if v.size == 0 or v.shape != q.shape:
                continue
            vn = float(np.linalg.norm(v)) or 1.0
            sim = float(np.dot(q, v) / (qn * vn))
            tid = row.get("id")
            if tid:
                scored.append((str(tid), sim))
        scored.sort(key=lambda x: -x[1])
        return scored[:k]

    def create_field(
        self,
        topic_id: str,
        field_name: str,
        *,
        field_type: str = "string",
        ref_topic_id: str | None = None,
        initial_entry: FieldHistoryEntry | None = None,
        validate_ref: bool = True,
        if_not_exists: bool = True,
    ) -> None:
        if validate_ref and ref_topic_id and not self.topic_exists(ref_topic_id):
            raise ValueError(f"ref_topic_id not found: {ref_topic_id}")
        tf = self._get_topic_fields(topic_id)
        if field_name in tf.fields and not if_not_exists:
            raise ValueError(f"field already exists: {field_name}")
        hist: list[FieldHistoryEntry] = []
        if initial_entry:
            e = initial_entry if initial_entry.id else initial_entry.model_copy(update={"id": str(uuid.uuid4())})
            hist = [e]
        tf.fields[field_name] = TopicField(
            field_type=field_type,
            ref_topic_id=ref_topic_id,
            history=hist,
        )
        self._set_topic_fields(topic_id, tf)

    def get_field(self, topic_id: str, field_name: str) -> TopicField | None:
        """Current value only: history length 0 or 1 (newest)."""
        tf = self._get_topic_fields(topic_id)
        if field_name not in tf.fields:
            if self._field_head_exists(topic_id, field_name):
                self.migrate_legacy_field_chains_to_json(topic_id, max_history=500)
                tf = self._get_topic_fields(topic_id)
            else:
                return None
        rec = tf.fields.get(field_name)
        if not rec:
            return None
        cur = rec.history[0] if rec.history else None
        h = [cur] if cur else []
        return TopicField(field_type=rec.field_type, ref_topic_id=rec.ref_topic_id, history=h)

    def get_field_with_history(self, topic_id: str, field_name: str) -> TopicField | None:
        tf = self._get_topic_fields(topic_id)
        if field_name not in tf.fields:
            if self._field_head_exists(topic_id, field_name):
                self.migrate_legacy_field_chains_to_json(topic_id, max_history=500)
                tf = self._get_topic_fields(topic_id)
            else:
                return None
        return tf.fields.get(field_name)

    def append_field_history(
        self,
        topic_id: str,
        field_name: str,
        entry: FieldHistoryEntry,
        *,
        field_type: str | None = None,
        ref_topic_id: str | None | object = _UNSET,
        max_history: int = 500,
        validate_ref: bool = True,
        create_if_missing: bool = True,
    ) -> str:
        if not entry.id:
            entry = entry.model_copy(update={"id": str(uuid.uuid4())})
        if ref_topic_id is not _UNSET and validate_ref and ref_topic_id:
            if not self.topic_exists(str(ref_topic_id)):
                raise ValueError(f"ref_topic_id not found: {ref_topic_id}")
        tf = self._get_topic_fields(topic_id)
        if field_name not in tf.fields:
            if not create_if_missing:
                raise ValueError(f"field not found: {field_name}")
            tf.fields[field_name] = TopicField(
                field_type=field_type or "string",
                ref_topic_id=None if ref_topic_id is _UNSET else (ref_topic_id or None),
                history=[],
            )
        rec = tf.fields[field_name]
        if field_type is not None:
            rec.field_type = field_type  # type: ignore[assignment]
        if ref_topic_id is not _UNSET:
            rec.ref_topic_id = ref_topic_id if ref_topic_id else None
        rec.history.insert(0, entry)
        if len(rec.history) > max_history:
            rec.history = rec.history[:max_history]
        self._set_topic_fields(topic_id, tf)
        self.sync_topic_salience_from_fields(topic_id)
        return str(entry.id)

    def set_field_ref(
        self,
        topic_id: str,
        field_name: str,
        ref_topic_id: str | None,
        *,
        validate_ref: bool = True,
        create_if_missing: bool = True,
    ) -> None:
        if validate_ref and ref_topic_id and not self.topic_exists(ref_topic_id):
            raise ValueError(f"ref_topic_id not found: {ref_topic_id}")
        tf = self._get_topic_fields(topic_id)
        if field_name not in tf.fields:
            if not create_if_missing:
                raise ValueError(f"field not found: {field_name}")
            tf.fields[field_name] = TopicField(ref_topic_id=ref_topic_id)
        else:
            tf.fields[field_name].ref_topic_id = ref_topic_id
        self._set_topic_fields(topic_id, tf)
        self.sync_topic_salience_from_fields(topic_id)

    def update_field(
        self,
        topic_id: str,
        field_name: str,
        *,
        field_type: str | None = None,
        ref_topic_id: str | None | object = _UNSET,
        new_entry: FieldHistoryEntry | None = None,
        max_history: int = 500,
        validate_ref: bool = True,
    ) -> str | None:
        if new_entry:
            return self.append_field_history(
                topic_id,
                field_name,
                new_entry,
                field_type=field_type,
                ref_topic_id=ref_topic_id,
                max_history=max_history,
                validate_ref=validate_ref,
                create_if_missing=True,
            )
        tf = self._get_topic_fields(topic_id)
        if field_name not in tf.fields:
            tf.fields[field_name] = TopicField()
        rec = tf.fields[field_name]
        if field_type is not None:
            rec.field_type = field_type  # type: ignore[assignment]
        if ref_topic_id is not _UNSET:
            if validate_ref and ref_topic_id and not self.topic_exists(str(ref_topic_id)):
                raise ValueError(f"ref_topic_id not found: {ref_topic_id}")
            rec.ref_topic_id = ref_topic_id if ref_topic_id else None
        self._set_topic_fields(topic_id, tf)
        self.sync_topic_salience_from_fields(topic_id)
        return None

    def delete_field(self, topic_id: str, field_name: str) -> None:
        tf = self._get_topic_fields(topic_id)
        if field_name in tf.fields:
            del tf.fields[field_name]
            self._set_topic_fields(topic_id, tf)
            self.sync_topic_salience_from_fields(topic_id)

    def list_field_names(self, topic_id: str) -> list[str]:
        return self.list_fields_for_topic(topic_id)

    def add_relationship(self, from_id: str, to_id: str, kind: str) -> None:
        self.add_related_edge(from_id, to_id, kind)

    def remove_relationship(self, from_id: str, to_id: str, kind: str) -> None:
        self._q(
            """
            MATCH (a:Topic {id: $a})-[r:RELATED {kind: $kind}]->(b:Topic {id: $b})
            DELETE r
            """,
            {"a": from_id, "b": to_id, "kind": kind},
        )

    def list_relationships(self, topic_id: str, *, direction: str = "both") -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if direction in ("out", "both"):
            r = self._q(
                """
                MATCH (t:Topic {id: $id})-[rel:RELATED]->(n:Topic)
                RETURN n.id AS id, n.title AS title, rel.kind AS kind, 'out' AS direction
                """,
                {"id": topic_id},
                read_only=True,
            )
            out.extend(_rows(r))
        if direction in ("in", "both"):
            r2 = self._q(
                """
                MATCH (t:Topic {id: $id})<-[rel:RELATED]-(n:Topic)
                RETURN n.id AS id, n.title AS title, rel.kind AS kind, 'in' AS direction
                """,
                {"id": topic_id},
                read_only=True,
            )
            out.extend(_rows(r2))
        return out

    def delete_topic(self, topic_id: str) -> None:
        self._q("MATCH (t:Topic {id: $id}) DETACH DELETE t", {"id": topic_id})

    def list_topic_ids(
        self, *, include_archived: bool = False, topic_kind: str | None = None
    ) -> list[str]:
        if topic_kind is not None and str(topic_kind).strip() != "":
            tk = str(topic_kind).strip()
            r = self._q(
                "MATCH (t:Topic {topic_kind: $tk}) RETURN t.id AS id, t.archived AS archived",
                {"tk": tk},
                read_only=True,
            )
        else:
            r = self._q(
                "MATCH (t:Topic) RETURN t.id AS id, t.archived AS archived",
                read_only=True,
            )
        rows = _rows(r)
        if not include_archived:
            rows = [x for x in rows if not x.get("archived")]
        return [str(x["id"]) for x in rows if x.get("id")]

    def list_topics_meta(
        self, *, include_archived: bool = False, topic_kind: str | None = None
    ) -> list[dict[str, Any]]:
        """Id, title, summary, and light metadata for each topic (for LLM discovery)."""
        if topic_kind is not None and str(topic_kind).strip() != "":
            tk = str(topic_kind).strip()
            r = self._q(
                """
                MATCH (t:Topic {topic_kind: $tk})
                RETURN t.id AS id, t.title AS title, t.summary AS summary,
                       t.topic_kind AS topic_kind, t.archived AS archived
                """,
                {"tk": tk},
                read_only=True,
            )
        else:
            r = self._q(
                """
                MATCH (t:Topic)
                RETURN t.id AS id, t.title AS title, t.summary AS summary,
                       t.topic_kind AS topic_kind, t.archived AS archived
                """,
                read_only=True,
            )
        rows = _rows(r)
        if not include_archived:
            rows = [x for x in rows if not x.get("archived")]
        out: list[dict[str, Any]] = []
        for x in rows:
            tid = x.get("id")
            if not tid:
                continue
            out.append(
                {
                    "id": str(tid),
                    "title": x.get("title"),
                    "summary": x.get("summary"),
                    "topic_kind": x.get("topic_kind"),
                    "archived": bool(x.get("archived")),
                }
            )
        return out

    def migrate_legacy_field_chains_to_json(self, topic_id: str, *, max_history: int = 500) -> int:
        """Copy legacy FieldHead/FieldVersion chains into fields_json. Returns fields migrated."""
        names = [
            str(row["name"])
            for row in _rows(
                self._q(
                    """
                    MATCH (t:Topic {id: $id})-[:HAS_FIELD]->(fh:FieldHead)
                    RETURN fh.field_name AS name
                    """,
                    {"id": topic_id},
                    read_only=True,
                )
            )
            if row.get("name")
        ]
        tf = self._get_topic_fields(topic_id)
        n = 0
        for field_name in names:
            if field_name in tf.fields and tf.fields[field_name].history:
                continue
            cur, hist = self._legacy_field_current_and_history(topic_id, field_name)
            if not cur and not hist:
                continue
            entries: list[FieldHistoryEntry] = []
            for h in hist:
                entries.append(
                    FieldHistoryEntry(
                        id=str(h.get("id") or str(uuid.uuid4())),
                        valid_from=str(h.get("valid_from") or ""),
                        value=h.get("value"),
                        provenance=str(h.get("provenance") or "legacy"),
                    )
                )
            tf.fields[field_name] = TopicField(field_type="string", history=entries[:max_history])
            n += 1
        if n:
            self._set_topic_fields(topic_id, tf)
        return n

    def add_field_version(
        self,
        topic_id: str,
        field_name: str,
        value: str,
        provenance: str,
        version_id: str | None = None,
        *,
        max_history: int = 500,
    ) -> str:
        """Append a value revision in `fields_json` (preferred storage)."""
        if not self.topic_exists(topic_id):
            raise ValueError(f"Topic not found: {topic_id}")
        entry = new_history_entry(
            value=value,
            valid_from=_now_iso(),
            provenance=provenance,
        )
        if version_id:
            entry = entry.model_copy(update={"id": version_id})
        return self.append_field_history(
            topic_id,
            field_name,
            entry,
            field_type="string",
            max_history=max_history,
        )

    def _field_head_exists(self, topic_id: str, field_name: str) -> bool:
        r = self._q(
            """
            MATCH (t:Topic {id: $topic_id})-[:HAS_FIELD {name: $field_name}]->(:FieldHead)
            RETURN count(t) AS c
            """,
            {"topic_id": topic_id, "field_name": field_name},
            read_only=True,
        )
        row = _row1(r)
        return bool(row and int(row.get("c", 0)) >= 1)

    def add_related_edge(self, from_id: str, to_id: str, kind: str) -> None:
        self._q(
            """
            MATCH (a:Topic {id: $a}), (b:Topic {id: $b})
            MERGE (a)-[:RELATED {kind: $kind}]->(b)
            """,
            {"a": from_id, "b": to_id, "kind": kind},
        )

    def list_topics_for_embedding_scan(self, include_archived: bool = False) -> list[dict[str, Any]]:
        r = self._q(
            """
            MATCH (t:Topic)
            RETURN t.id AS id, t.title AS title, t.summary AS summary,
                   t.embedding AS embedding, t.embedding_json AS embedding_json,
                   t.salience AS salience, t.failed_salience AS failed_salience,
                   t.topic_history_json AS topic_history_json,
                   t.archived AS archived
            """,
            read_only=True,
        )
        rows = _rows(r)
        if not include_archived:
            rows = [x for x in rows if not x.get("archived")]
        return rows

    def neighbors(self, topic_id: str, depth: int = 1) -> list[dict[str, Any]]:
        _ = depth
        r2 = self._q(
            """
            MATCH (t:Topic {id: $id})-[:RELATED]-(n:Topic)
            RETURN DISTINCT n.id AS id, n.title AS title
            """,
            {"id": topic_id},
            read_only=True,
        )
        return _rows(r2)

    def field_current_and_history(
        self, topic_id: str, field_name: str
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        tf = self._get_topic_fields(topic_id)
        if field_name in tf.fields and tf.fields[field_name].history:
            rec = tf.fields[field_name]
            cur_e = rec.history[0]
            current = {
                "id": cur_e.id,
                "value": cur_e.value,
                "valid_from": cur_e.valid_from,
                "provenance": cur_e.provenance,
                "why_changed": cur_e.why_changed,
                "impact_expected": cur_e.impact_expected,
            }
            hist = [
                {
                    "id": e.id,
                    "value": e.value,
                    "valid_from": e.valid_from,
                    "provenance": e.provenance,
                    "why_changed": e.why_changed,
                    "impact_expected": e.impact_expected,
                }
                for e in rec.history
            ]
            return current, hist
        if self._field_head_exists(topic_id, field_name):
            return self._legacy_field_current_and_history(topic_id, field_name)
        return None, []

    def _legacy_field_current_and_history(
        self, topic_id: str, field_name: str
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        r = self._q(
            """
            MATCH (t:Topic {id: $topic_id})-[:HAS_FIELD {name: $field_name}]->(fh:FieldHead)
            OPTIONAL MATCH (fh)-[:LATEST]->(cur:FieldVersion)
            RETURN cur.id AS id, cur.value AS value, cur.valid_from AS valid_from, cur.provenance AS provenance
            """,
            {"topic_id": topic_id, "field_name": field_name},
            read_only=True,
        )
        cur_row = _row1(r)
        current = None
        if cur_row and cur_row.get("id"):
            current = {
                "id": cur_row["id"],
                "value": cur_row.get("value"),
                "valid_from": cur_row.get("valid_from"),
                "provenance": cur_row.get("provenance"),
            }
        hist: list[dict[str, Any]] = []
        if current:
            hist = self._walk_history(topic_id, field_name)
        return current, hist

    def _walk_history(self, topic_id: str, field_name: str) -> list[dict[str, Any]]:
        r = self._q(
            """
            MATCH (t:Topic {id: $topic_id})-[:HAS_FIELD {name: $field_name}]->(fh:FieldHead)
            MATCH (fh)-[:LATEST]->(cur:FieldVersion)
            RETURN cur.id AS id, cur.value AS value, cur.valid_from AS valid_from, cur.provenance AS provenance
            """,
            {"topic_id": topic_id, "field_name": field_name},
            read_only=True,
        )
        row = _row1(r)
        if not row or not row.get("id"):
            return []
        chain: list[dict[str, Any]] = []
        cur_id = row["id"]
        cur_val = row
        while cur_id:
            chain.append(
                {
                    "id": cur_val["id"],
                    "value": cur_val.get("value"),
                    "valid_from": cur_val.get("valid_from"),
                    "provenance": cur_val.get("provenance"),
                }
            )
            r2 = self._q(
                """
                MATCH (fv:FieldVersion {id: $id})-[:PREV]->(prev:FieldVersion)
                RETURN prev.id AS id, prev.value AS value, prev.valid_from AS valid_from, prev.provenance AS provenance
                """,
                {"id": cur_id},
                read_only=True,
            )
            prev = _row1(r2)
            if not prev or not prev.get("id"):
                break
            cur_id = prev["id"]
            cur_val = prev
        return chain

    def list_fields_for_topic(self, topic_id: str) -> list[str]:
        names = set(self._get_topic_fields(topic_id).fields.keys())
        r = self._q(
            """
            MATCH (t:Topic {id: $id})-[:HAS_FIELD]->(fh:FieldHead)
            RETURN fh.field_name AS name
            """,
            {"id": topic_id},
            read_only=True,
        )
        for row in _rows(r):
            if row.get("name"):
                names.add(str(row["name"]))
        return sorted(names)

    def count_topics(self) -> int:
        r = self._q("MATCH (t:Topic) RETURN count(t) AS c", read_only=True)
        row = _row1(r)
        return int(row["c"]) if row else 0

    def find_duplicate_titles(self) -> list[tuple[str, str, str]]:
        """Return (title, id_a, id_b) pairs for revise heuristic."""
        r = self._q(
            """
            MATCH (a:Topic), (b:Topic)
            WHERE a.id < b.id AND a.title = b.title AND a.title <> ''
            RETURN a.title AS title, a.id AS id_a, b.id AS id_b
            LIMIT 50
            """,
            read_only=True,
        )
        return [(str(x["title"]), str(x["id_a"]), str(x["id_b"])) for x in _rows(r)]

    def merge_topics(self, keep_id: str, drop_id: str) -> None:
        """Merge RELATED edges, fields_json, then legacy field heads; delete drop."""
        self._q(
            """
            MATCH (d:Topic {id: $drop})-[r:RELATED]->(x:Topic)
            MATCH (k:Topic {id: $keep})
            MERGE (k)-[nr:RELATED {kind: r.kind}]->(x)
            DELETE r
            """,
            {"keep": keep_id, "drop": drop_id},
        )
        self._q(
            """
            MATCH (x:Topic)-[r:RELATED]->(d:Topic {id: $drop})
            MATCH (k:Topic {id: $keep})
            MERGE (x)-[nr:RELATED {kind: r.kind}]->(k)
            DELETE r
            """,
            {"keep": keep_id, "drop": drop_id},
        )
        k_tf = self._get_topic_fields(keep_id)
        d_tf = self._get_topic_fields(drop_id)
        for name, rec in d_tf.fields.items():
            if name not in k_tf.fields:
                k_tf.fields[name] = rec
        self._set_topic_fields(keep_id, k_tf)
        fields = self.list_fields_for_topic(drop_id)
        for fn in fields:
            existing = self.list_fields_for_topic(keep_id)
            if fn in existing:
                continue
            self._q(
                """
                MATCH (d:Topic {id: $drop})-[old:HAS_FIELD {name: $fn}]->(fh:FieldHead)
                MATCH (k:Topic {id: $keep})
                CREATE (k)-[:HAS_FIELD {name: $fn}]->(fh)
                SET fh.topic_id = $keep
                DELETE old
                """,
                {"drop": drop_id, "keep": keep_id, "fn": fn},
            )
        self._q("MATCH (t:Topic {id: $id}) DETACH DELETE t", {"id": drop_id})


def get_graph(settings: Settings | None = None) -> KuzuGraph:
    return get_kuzu_graph(settings or get_settings())


def get_store(settings: Settings | None = None) -> GraphStore:
    g = get_graph(settings)
    store = GraphStore(g)
    store.init_schema()
    return store
