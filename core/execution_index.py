from __future__ import annotations

from dataclasses import dataclass, field

from core.event import Transfer
from core.resource_index import ResourceIndex


@dataclass
class ExecutionIndex:
    """
    Execution-level index for detecting candidate interactions.

    Resource overlap means that two events may interact.
    It does not classify the interaction as causal, compatible,
    order-dependent, or conflicting.
    """

    _index: ResourceIndex = field(
        default_factory=ResourceIndex
    )

    def add(self, event: Transfer) -> None:
        self._index.add(event)

    def add_all(self, events) -> None:
        self._index.add_all(events)

    def contains(self, event: Transfer) -> bool:
        return event.event_id() in self._index._events

    def overlaps(
        self,
        event: Transfer,
    ) -> tuple[Transfer, ...]:
        return self._index.overlapping_events(event)

    def independent(
        self,
        event: Transfer,
    ) -> bool:
        return not self._index.overlapping_event_ids(event)

    def __len__(self) -> int:
        return len(self._index)

    @property
    def resource_count(self) -> int:
        return self._index.resource_count
