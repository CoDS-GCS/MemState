from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from memstate.core.executor import Executor
from memstate.core.models import Policies


ReasonerEvent = Literal["ingest_complete", "query_complete", "cron", "memory_pressure"]


@dataclass
class ReasonerResult:
    revise_actions: list[str] = field(default_factory=list)
    forget_actions: list[str] = field(default_factory=list)


class Reasoner:
    """
    Inspects memory (read-only via Executor.store) and triggers internal revise / forget.
    v1: rule-based only.
    """

    def __init__(self, executor: Executor, policies: Policies | None = None) -> None:
        self._ex = executor
        self._p = policies or executor.policies

    def run(self, event: ReasonerEvent) -> ReasonerResult:
        out = ReasonerResult()
        n = self._ex.store.count_topics()

        if event in ("ingest_complete", "cron", "memory_pressure"):
            if n >= self._p.topic_count_soft_limit or event == "memory_pressure":
                out.forget_actions.extend(self._ex.run_forget_low_salience())
            if n > 0 and event in ("ingest_complete", "cron"):
                out.revise_actions.extend(self._ex.run_revise_duplicates())

        if event == "query_complete" and n >= self._p.topic_count_soft_limit:
            out.forget_actions.extend(self._ex.run_forget_low_salience())

        return out
