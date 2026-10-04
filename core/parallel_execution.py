from __future__ import annotations

from dataclasses import dataclass

from core.event import Transfer
from core.execution_index import ExecutionIndex


@dataclass
class ParallelExecution:
    events: tuple[Transfer, ...]

    def __post_init__(self):
        self._index = ExecutionIndex()
        self._index.add_all(self.events)

    @property
    def event_ids(self) -> tuple[str, ...]:
        return tuple(event.event_id() for event in self.events)

    def is_parallel(
        self,
        first: Transfer,
        second: Transfer,
    ) -> bool:
        if first.event_id() == second.event_id():
            return False

        if not self._index.contains(second):
            return False

        return self._index.independent(first)
