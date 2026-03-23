"""Split long user text into overlapping segments (same semantics as the UI chunk helpers)."""

from __future__ import annotations


def chunk_text_with_overlap(text: str, max_len: int, overlap: int) -> list[str]:
    """
    Split ``text`` into chunks of at most ``max_len`` characters, advancing by
    ``max_len - overlap`` between chunks (except the last).
    """
    t = text
    if len(t) <= max_len:
        return [t]
    if overlap >= max_len:
        return [t]
    chunks: list[str] = []
    start = 0
    length = len(t)
    while start < length:
        end = min(start + max_len, length)
        chunks.append(t[start:end])
        if end == length:
            break
        nxt = end - overlap
        start = nxt if nxt > start else end
    return chunks


def build_internal_chunk_user_message(
    chunk: str,
    index1: int,
    total: int,
    overlap: int,
) -> str:
    """Server-only segment wrapper (not shown as separate chat bubbles in the UI)."""
    if total <= 1:
        return chunk
    return (
        f"[Internal segment {index1}/{total} — long message; ~{overlap} chars overlap between "
        "adjacent segments for continuity. Integrate with the graph; do not duplicate entities or "
        "whole topics already created in a prior segment.]\n\n---\n\n"
        f"{chunk}"
    )
