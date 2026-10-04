from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from core.event import Transfer
from core.resource_support import transfer_resource_support


@dataclass
class ResourceIndex:
    """
    Index events by their semantic state resources.

    The index detects potential interaction through resource overlap.
    It does not decide whether overlapping events are compatible,
    order-dependent, or conflicting.
    """

    _by_resource: dict[str, set[str]] = field(
        default_factory=lambda: defaultdict(set)
    )
    _events: dict[str, Transfer] = field(default_factory=dict)

    def add(self, event: Transfer) -> None:
        event_id = event.event_id()

        if event_id in self._events:
            return

        self._events[event_id] = event

        support = transfer_resource_support(event)

        for resource in support.resources:
            self._by_resource[resource].add(event_id)

    def add_all(self, events) -> None:
        for event in events:
            self.add(event)

    def events_for_resource(self, resource: str) -> frozenset[str]:
        return frozenset(
            self._by_resource.get(resource, set())
        )

    def overlapping_event_ids(
        self,
        event: Transfer,
    ) -> frozenset[str]:
        event_id = event.event_id()
        overlapping = set()

        support = transfer_resource_support(event)

        for resource in support.resources:
            overlapping.update(
                self._by_resource.get(resource, set())
            )

        overlapping.discard(event_id)

        return frozenset(overlapping)

    def overlapping_events(
        self,
        event: Transfer,
    ) -> tuple[Transfer, ...]:
        ids = self.overlapping_event_ids(event)

        return tuple(
            self._events[event_id]
            for event_id in sorted(ids)
        )

    def __len__(self) -> int:
        return len(self._events)

    @property
    def resource_count(self) -> int:
        return len(self._by_resource)
