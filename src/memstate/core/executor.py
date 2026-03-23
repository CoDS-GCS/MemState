from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import numpy as np

from memstate.core.models import (
    FieldOut,
    FieldVersionOut,
    IngestRequest,
    IngestResponse,
    Policies,
    QueryRequest,
    QueryResponse,
    TopicBundle,
)
from memstate.datamodel.fields import new_history_entry
from memstate.datamodel.mappers import topic_from_graph_row
from memstate.embeddings import default_text_embedder
from memstate.embeddings.base import EmbeddingProvider
from memstate.store.graph_store import REF_UNCHANGED, GraphStore

if TYPE_CHECKING:
    pass


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cosine_top_k(
    query_vec: np.ndarray, vectors: list[tuple[str, np.ndarray]], k: int
) -> list[tuple[str, float]]:
    if not vectors:
        return []
    q = query_vec / (np.linalg.norm(query_vec) or 1.0)
    scored: list[tuple[str, float]] = []
    for tid, v in vectors:
        n = np.linalg.norm(v) or 1.0
        sim = float(np.dot(q, v / n))
        scored.append((tid, sim))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:k]


class Executor:
    """Block 2 — validated transitions into GraphStore."""

    def __init__(
        self,
        store: GraphStore,
        policies: Policies | None = None,
        embedder: EmbeddingProvider | None = None,
    ) -> None:
        self._store = store
        self._p = policies or Policies()
        self._emb = embedder or default_text_embedder(self._p.embedding_dimension)

    @property
    def store(self) -> GraphStore:
        return self._store

    @property
    def policies(self) -> Policies:
        return self._p

    def _topic_text_for_embed(self, title: str, summary: str) -> str:
        return f"{title}\n{summary or ''}".strip()

    def _load_embedding_vectors(self) -> list[tuple[str, np.ndarray]]:
        rows = self._store.list_topics_for_embedding_scan(include_archived=False)
        out: list[tuple[str, np.ndarray]] = []
        for row in rows:
            node = topic_from_graph_row(row)
            if not node or not node.embedding:
                continue
            vec = np.array(node.embedding, dtype=np.float64)
            if vec.size == self._emb.dimension:
                out.append((str(row["id"]), vec))
        return out

    def ingest(self, req: IngestRequest) -> IngestResponse:
        applied: list[str] = []
        version_ids: dict[str, str] = {}
        similar: list[str] = []

        if req.suggest_similar:
            text = self._topic_text_for_embed(req.title, req.summary or "")
            qv = np.array(self._emb.embed([text])[0])
            k = 8
            knn = self._store.vector_knn_topic_ids(qv.tolist(), k=k)
            if knn:
                similar = [t for t, _ in knn]
            else:
                loaded_sim = self._load_embedding_vectors()
                similar = [
                    t
                    for t, _ in _cosine_top_k(
                        qv, loaded_sim, k=min(k, max(1, len(loaded_sim)))
                    )
                ]

        if req.placement == "new_topic":
            tid = str(uuid.uuid4())
            text = self._topic_text_for_embed(req.title, req.summary or "")
            vec = self._emb.embed([text])[0]
            self._store.create_topic(
                tid,
                title=req.title or "untitled",
                summary=req.summary,
                salience=req.salience,
                archived=False,
                embedding=vec,
                topic_kind=req.topic_kind,
            )
            applied.append(f"created_topic:{tid}")
            for fw in req.fields:
                entry = new_history_entry(
                    value=fw.value,
                    valid_from=_utc_iso(),
                    provenance=fw.provenance,
                    why_changed=fw.why_changed,
                    impact_expected=fw.impact_expected,
                )
                ref_kw = REF_UNCHANGED
                if fw.ref_topic_id is not None:
                    ref_kw = fw.ref_topic_id
                vid = self._store.append_field_history(
                    tid,
                    fw.name,
                    entry,
                    field_type=fw.field_type,
                    ref_topic_id=ref_kw,
                    max_history=self._p.max_field_history,
                )
                version_ids[fw.name] = vid
                applied.append(f"field:{fw.name}")
            for e in req.edges:
                self._store.add_related_edge(tid, e.to_topic_id, e.kind)
                applied.append(f"edge:{e.to_topic_id}")
            return IngestResponse(
                topic_id=tid, applied=applied, version_ids=version_ids, similar_topic_ids=similar
            )

        if req.placement == "extend_topic":
            if not req.topic_id:
                raise ValueError("extend_topic requires topic_id")
            if not self._store.topic_exists(req.topic_id):
                raise ValueError("topic not found")
            tid = req.topic_id
            for fw in req.fields:
                entry = new_history_entry(
                    value=fw.value,
                    valid_from=_utc_iso(),
                    provenance=fw.provenance,
                    why_changed=fw.why_changed,
                    impact_expected=fw.impact_expected,
                )
                ref_kw = REF_UNCHANGED
                if fw.ref_topic_id is not None:
                    ref_kw = fw.ref_topic_id
                vid = self._store.append_field_history(
                    tid,
                    fw.name,
                    entry,
                    field_type=fw.field_type,
                    ref_topic_id=ref_kw,
                    max_history=self._p.max_field_history,
                )
                version_ids[fw.name] = vid
                applied.append(f"field:{fw.name}")
            t = self._store.get_topic(tid)
            if t:
                text = self._topic_text_for_embed(
                    str(t.get("title") or ""), str(t.get("summary") or "")
                )
                vec = self._emb.embed([text])[0]
                self._store.update_topic_embedding(tid, vec)
            for e in req.edges:
                self._store.add_related_edge(tid, e.to_topic_id, e.kind)
                applied.append(f"edge:{e.to_topic_id}")
            return IngestResponse(
                topic_id=tid, applied=applied, version_ids=version_ids, similar_topic_ids=similar
            )

        if req.placement == "version_field":
            if not req.topic_id or len(req.fields) != 1:
                raise ValueError("version_field requires topic_id and exactly one field")
            if not self._store.topic_exists(req.topic_id):
                raise ValueError("topic not found")
            fw = req.fields[0]
            entry = new_history_entry(
                value=fw.value,
                valid_from=_utc_iso(),
                provenance=fw.provenance,
                why_changed=fw.why_changed,
                impact_expected=fw.impact_expected,
            )
            ref_kw = REF_UNCHANGED
            if fw.ref_topic_id is not None:
                ref_kw = fw.ref_topic_id
            vid = self._store.append_field_history(
                req.topic_id,
                fw.name,
                entry,
                field_type=fw.field_type,
                ref_topic_id=ref_kw,
                max_history=self._p.max_field_history,
            )
            version_ids[fw.name] = vid
            applied.append(f"version:{fw.name}")
            t = self._store.get_topic(req.topic_id)
            if t:
                text = self._topic_text_for_embed(
                    str(t.get("title") or ""), str(t.get("summary") or "")
                )
                vec = self._emb.embed([text])[0]
                self._store.update_topic_embedding(req.topic_id, vec)
            return IngestResponse(
                topic_id=req.topic_id,
                applied=applied,
                version_ids=version_ids,
                similar_topic_ids=similar,
            )

        raise ValueError("unknown placement")

    def _field_bundle(
        self, tid: str, fn: str, req: QueryRequest
    ) -> FieldOut | None:
        tf = self._store.get_field_with_history(tid, fn)
        if not tf:
            return None
        cur_e = tf.current_entry()
        want_temporal = "temporal" in req.stages
        want_structural = "structural" in req.stages
        if want_structural and not want_temporal and not cur_e:
            return None
        cur_out = None
        if cur_e:
            cur_out = FieldVersionOut(
                id=cur_e.id,
                value=cur_e.value,
                valid_from=cur_e.valid_from or None,
                provenance=cur_e.provenance,
                why_changed=cur_e.why_changed,
                impact_expected=cur_e.impact_expected,
            )
        hist_out: list[FieldVersionOut] = []
        if want_temporal and req.explain:
            hist_out = [
                FieldVersionOut(
                    id=e.id,
                    value=e.value,
                    valid_from=e.valid_from or None,
                    provenance=e.provenance,
                    why_changed=e.why_changed,
                    impact_expected=e.impact_expected,
                )
                for e in tf.history
            ]
        elif cur_out:
            hist_out = [cur_out]
        if not cur_out and not hist_out:
            return None
        return FieldOut(
            name=fn,
            field_type=tf.field_type,
            ref_topic_id=tf.ref_topic_id,
            current=cur_out,
            history=hist_out,
        )

    def query(self, req: QueryRequest) -> QueryResponse:
        qv = np.array(self._emb.embed([req.q])[0])
        loaded = self._load_embedding_vectors()
        sim_map: dict[str, float] = {}
        if "semantic" in req.stages:
            knn = self._store.vector_knn_topic_ids(qv.tolist(), k=req.top_k)
            if knn:
                candidate_ids = [t for t, _ in knn]
                sim_map = dict(knn)
            elif loaded:
                ranked = _cosine_top_k(qv, loaded, k=req.top_k)
                candidate_ids = [t for t, _ in ranked]
                sim_map = dict(ranked)
            elif req.topic_ids:
                candidate_ids = list(req.topic_ids)[: req.top_k]
            else:
                candidate_ids = []
        elif req.topic_ids:
            candidate_ids = list(req.topic_ids)[: req.top_k]
        else:
            candidate_ids = [t for t, _ in loaded][: req.top_k]

        if req.topic_ids and "semantic" in req.stages:
            allow = set(req.topic_ids)
            candidate_ids = [c for c in candidate_ids if c in allow][: req.top_k]

        bundles: list[TopicBundle] = []
        for tid in candidate_ids:
            t = self._store.get_topic(tid)
            if not t:
                continue
            if t.get("archived"):
                continue
            tk = t.get("topic_kind")
            bundle = TopicBundle(
                topic_id=tid,
                title=str(t.get("title") or ""),
                summary=str(t.get("summary") or "") or None,
                topic_kind=str(tk) if tk else None,
                salience=float(t.get("salience") or 0),
                failed_salience=float(t.get("failed_salience") or 0),
                similarity=sim_map.get(tid) if "semantic" in req.stages else None,
            )
            if "structural" in req.stages:
                bundle.neighbors = self._store.neighbors(tid)
            if "structural" in req.stages or "temporal" in req.stages:
                fnames = req.field_names or self._store.list_fields_for_topic(tid)
                for fn in fnames:
                    fo = self._field_bundle(tid, fn, req)
                    if fo:
                        bundle.fields.append(fo)
            bundles.append(bundle)
            old_sal = float(t.get("salience") or 0)
            new_sal = old_sal + self._p.query_salience_bump
            new_sal = min(new_sal, 1e9)
            self._store.update_topic_meta(tid, salience=new_sal)
            self._store.append_topic_history(
                tid,
                {
                    "ts": _utc_iso(),
                    "kind": "salience",
                    "detail": {"from": old_sal, "to": new_sal, "reason": "query_bump"},
                },
            )

        lines = [f"Top topics for {req.q!r}:"]
        for b in bundles[:5]:
            lines.append(f"- {b.topic_id} {b.title!r} sim={b.similarity}")
        return QueryResponse(query=req.q, candidates=bundles, summary_text="\n".join(lines))

    def run_revise_duplicates(self) -> list[str]:
        actions: list[str] = []
        for title, id_a, id_b in self._store.find_duplicate_titles():
            self._store.merge_topics(keep_id=id_a, drop_id=id_b)
            actions.append(f"merged:{id_b}->:{id_a}:{title}")
        return actions

    def run_forget_low_salience(self) -> list[str]:
        rows = self._store.list_topics_for_embedding_scan(include_archived=False)
        actions: list[str] = []
        for row in rows:
            sal = float(row.get("salience") or 0)
            tid = str(row["id"])
            if sal < self._p.forget_salience_threshold:
                self._store.update_topic_meta(tid, archived=True, salience=sal * 0.5)
                actions.append(f"archived:{tid}")
        return actions
