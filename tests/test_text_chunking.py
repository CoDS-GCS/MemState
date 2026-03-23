"""Chunking matches UI/server contract for long user messages."""

from memstate.llm.text_chunking import chunk_text_with_overlap


def test_chunk_text_single_when_short() -> None:
    assert chunk_text_with_overlap("abc", 10, 2) == ["abc"]


def test_chunk_text_overlap_advances() -> None:
    t = "a" * 10001
    parts = chunk_text_with_overlap(t, 10000, 800)
    assert len(parts) == 2
    assert len(parts[0]) == 10000
    assert parts[0].endswith("a" * 800)
    assert parts[1].startswith("a" * 800)
