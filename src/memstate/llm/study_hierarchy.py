"""Rule-based multi-level document units for Study ingest (no embeddings)."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

# cl100k_base: stable token counts comparable across runs (GPT-style).
try:
    import tiktoken

    _ENC = tiktoken.get_encoding("cl100k_base")
except Exception:  # pragma: no cover
    _ENC = None

_LEVEL_NAMES = ("coarse", "medium", "fine")

# Markdown ATX headings (line-start), or plain blocks when absent.
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def study_topic_kind(session_id: str) -> str:
    """Reserved ``topic_kind`` for topics created in a Study session."""
    return f"study:{session_id}"


def _token_count(text: str) -> int:
    if not text:
        return 0
    if _ENC is not None:
        return len(_ENC.encode(text))
    return max(1, len(text) // 4)


def _excerpt(s: str, max_len: int = 200) -> str:
    t = " ".join(s.split())
    if len(t) <= max_len:
        return t
    return t[: max_len - 1].rstrip() + "…"


def _split_sentences(paragraph: str) -> list[str]:
    """Lightweight sentence boundaries (no NLTK)."""
    p = paragraph.strip()
    if not p:
        return []
    parts = re.split(r"(?<=[.!?])\s+", p)
    return [x.strip() for x in parts if x.strip()]


def _split_paragraphs(block: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n+", block) if p.strip()]


def _has_markdown_headings(text: str) -> bool:
    for line in text.splitlines():
        if _HEADING_RE.match(line.strip()):
            return True
    return False


def _sections_from_markdown(text: str) -> list[tuple[str, str]]:
    """Return list of (heading_or_title, body) for each section."""
    lines = text.splitlines()
    sections: list[tuple[str, str]] = []
    cur_title = ""
    cur_lines: list[str] = []

    def flush() -> None:
        nonlocal cur_title, cur_lines
        body = "\n".join(cur_lines).strip()
        title = cur_title or "(document)"
        sections.append((title, body))
        cur_lines = []

    for line in lines:
        m = _HEADING_RE.match(line.strip())
        if m:
            if cur_title or cur_lines:
                flush()
            cur_title = m.group(2).strip()
            continue
        cur_lines.append(line)
    flush()
    if not sections:
        return [("(document)", text.strip())]
    return sections


def _sections_from_paragraphs(text: str) -> list[tuple[str, str]]:
    blocks = _split_paragraphs(text)
    if not blocks:
        return [("(document)", text.strip())]
    out: list[tuple[str, str]] = []
    for i, b in enumerate(blocks):
        title = f"Block {i + 1}"
        preview = _excerpt(b, 80)
        out.append((f"{title}: {preview}", b))
    return out


@dataclass
class StudyUnit:
    """One semantic unit at a given granularity level."""

    id: str
    level: int
    level_name: str
    parent_id: str | None
    text: str
    token_count: int
    context_before: str
    context_after: str


@dataclass
class StudyHierarchy:
    """Flat list of units with tree edges implied by parent_id + level."""

    units: list[StudyUnit] = field(default_factory=list)
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_catalog_dict(self, *, max_units: int | None = None) -> dict:
        ulist = self.units if max_units is None else self.units[:max_units]
        return {
            "session_id": self.session_id,
            "truncated": max_units is not None and len(self.units) > len(ulist),
            "total_units": len(self.units),
            "units": [
                {
                    "id": u.id,
                    "level": u.level,
                    "level_name": u.level_name,
                    "parent_id": u.parent_id,
                    "token_count": u.token_count,
                    "context_before": u.context_before,
                    "context_after": u.context_after,
                    "text_preview": _excerpt(u.text, 400),
                }
                for u in ulist
            ],
        }


def _assign_sibling_context(siblings: list[StudyUnit]) -> None:
    n = len(siblings)
    for i, u in enumerate(siblings):
        before = _excerpt(siblings[i - 1].text) if i > 0 else ""
        after = _excerpt(siblings[i + 1].text) if i < n - 1 else ""
        u.context_before = before
        u.context_after = after


def build_study_hierarchy(document: str, *, session_id: str | None = None) -> StudyHierarchy:
    """
    Build three levels: coarse (sections), medium (paragraphs), fine (sentences).
    Sibling context_before/context_after are excerpts of adjacent units at the same level.
    """
    doc = document.strip()
    sid = session_id or str(uuid.uuid4())
    units: list[StudyUnit] = []
    id_counter = 0

    def new_id() -> str:
        nonlocal id_counter
        id_counter += 1
        return f"su_{sid[:8]}_{id_counter}"

    if _has_markdown_headings(doc):
        sections = _sections_from_markdown(doc)
    else:
        sections = _sections_from_paragraphs(doc)

    coarse_siblings: list[StudyUnit] = []
    for sec_title, sec_body in sections:
        cid = new_id()
        coarse = StudyUnit(
            id=cid,
            level=0,
            level_name=_LEVEL_NAMES[0],
            parent_id=None,
            text=sec_body if sec_body else sec_title,
            token_count=_token_count(sec_body if sec_body else sec_title),
            context_before="",
            context_after="",
        )
        units.append(coarse)
        coarse_siblings.append(coarse)

        paras = _split_paragraphs(sec_body) if sec_body.strip() else [sec_body]
        if len(paras) == 1 and not paras[0].strip():
            continue
        medium_siblings: list[StudyUnit] = []
        for para in paras:
            pid = new_id()
            medium = StudyUnit(
                id=pid,
                level=1,
                level_name=_LEVEL_NAMES[1],
                parent_id=cid,
                text=para,
                token_count=_token_count(para),
                context_before="",
                context_after="",
            )
            units.append(medium)
            medium_siblings.append(medium)
            fine_siblings: list[StudyUnit] = []
            for sent in _split_sentences(para):
                fid = new_id()
                fine = StudyUnit(
                    id=fid,
                    level=2,
                    level_name=_LEVEL_NAMES[2],
                    parent_id=pid,
                    text=sent,
                    token_count=_token_count(sent),
                    context_before="",
                    context_after="",
                )
                units.append(fine)
                fine_siblings.append(fine)
            _assign_sibling_context(fine_siblings)
        _assign_sibling_context(medium_siblings)

    _assign_sibling_context(coarse_siblings)

    return StudyHierarchy(units=units, session_id=sid)


def format_study_catalog_for_prompt(h: StudyHierarchy, *, max_units: int = 200) -> str:
    """Bounded text block for the system/user message (avoids context overflow)."""
    lines: list[str] = [
        "Study unit catalog (rule-based hierarchy; levels: coarse → medium → fine).",
        f"session_id={h.session_id}",
        "",
    ]
    shown = h.units[:max_units]
    for u in shown:
        lines.append(
            f"- [{u.id}] {u.level_name} tokens={u.token_count} parent={u.parent_id or '—'}"
        )
        if u.context_before:
            lines.append(f"    before_neighbor: {u.context_before}")
        if u.context_after:
            lines.append(f"    after_neighbor: {u.context_after}")
        lines.append(f"    preview: {_excerpt(u.text, 320)}")
        lines.append("")
    if len(h.units) > max_units:
        lines.append(f"[… {len(h.units) - max_units} more units omitted; call study_unit_catalog if needed …]")
    return "\n".join(lines).strip()
