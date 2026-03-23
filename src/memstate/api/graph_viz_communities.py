"""Graph UI communities: merge structural edges (refs + RELATED) with semantic similarity (embeddings)."""

from __future__ import annotations

import numpy as np

# Tunable: union each topic with up to this many nearest neighbors by cosine similarity.
_SEMANTIC_TOP_K = 8
# Tunable: ignore neighbors weaker than this cosine similarity (after sorting by strength).
_SEMANTIC_MIN_SIM = 0.48


class _UnionFind:
    __slots__ = ("_p", "_r")

    def __init__(self, n: int) -> None:
        self._p = list(range(n))
        self._r = [0] * n

    def find(self, x: int) -> int:
        p = self._p
        if p[x] != x:
            p[x] = self.find(p[x])
        return p[x]

    def union(self, a: int, b: int) -> None:
        p, r = self._p, self._r
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if r[ra] < r[rb]:
            ra, rb = rb, ra
        p[rb] = ra
        if r[ra] == r[rb]:
            r[ra] += 1


def compute_topic_communities(
    topic_ids: list[str],
    structural_pairs: list[tuple[str, str]],
    embeddings: dict[str, list[float]],
    *,
    semantic_top_k: int = _SEMANTIC_TOP_K,
    semantic_min_sim: float = _SEMANTIC_MIN_SIM,
) -> dict[str, int]:
    """
    Assign each topic a community id (0 .. C-1).

    - Unions all undirected structural pairs (field refs + RELATED).
    - For topics with embeddings of a common dimension, unions each node with up to
      ``semantic_top_k`` nearest neighbors by cosine similarity, if similarity >=
      ``semantic_min_sim``.
    """
    n = len(topic_ids)
    if n == 0:
        return {}
    id_to_i = {tid: i for i, tid in enumerate(topic_ids)}
    uf = _UnionFind(n)

    for a, b in structural_pairs:
        ia = id_to_i.get(a)
        ib = id_to_i.get(b)
        if ia is not None and ib is not None:
            uf.union(ia, ib)

    # Embedding dimension: use most common length among stored vectors.
    lengths: list[int] = [len(v) for v in embeddings.values() if v]
    if not lengths:
        return _compress_labels(topic_ids, uf)

    dim = max(set(lengths), key=lengths.count)
    idx_emb: list[int] = []
    rows: list[list[float]] = []
    for i, tid in enumerate(topic_ids):
        ev = embeddings.get(tid)
        if ev and len(ev) == dim:
            idx_emb.append(i)
            rows.append([float(x) for x in ev])

    m = len(idx_emb)
    if m >= 2:
        e_mat = np.asarray(rows, dtype=np.float64)
        norms = np.linalg.norm(e_mat, axis=1, keepdims=True)
        norms = np.maximum(norms, 1e-12)
        en = e_mat / norms
        sim = en @ en.T
        k_cap = max(1, min(semantic_top_k, m - 1))
        for r in range(m):
            row = sim[r]
            order = np.argsort(-row)
            taken = 0
            for j in order:
                if j == r:
                    continue
                if float(row[j]) < semantic_min_sim:
                    break
                uf.union(idx_emb[r], idx_emb[j])
                taken += 1
                if taken >= k_cap:
                    break

    return _compress_labels(topic_ids, uf)


def _compress_labels(topic_ids: list[str], uf: _UnionFind) -> dict[str, int]:
    roots = [uf.find(i) for i in range(len(topic_ids))]
    remap: dict[int, int] = {}
    out: dict[str, int] = {}
    next_id = 0
    for tid, root in zip(topic_ids, roots, strict=True):
        if root not in remap:
            remap[root] = next_id
            next_id += 1
        out[tid] = remap[root]
    return out
