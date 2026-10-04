from dataclasses import dataclass

from core.event import Transfer


@dataclass(frozen=True)
class GraphSnapshot:
    events: tuple[Transfer, ...]
    frontier: frozenset[str]

    def event_ids(self) -> frozenset[str]:
        return frozenset(
            event.event_id()
            for event in self.events
        )

    def missing_parents(self) -> frozenset[str]:
        known = self.event_ids()
        missing = set()

        for event in self.events:
            for parent in event.parents:
                if parent not in known:
                    missing.add(parent)

        return frozenset(missing)

    def complete(self) -> bool:
        return not self.missing_parents()

    def contains(self, event_id: str) -> bool:
        return event_id in self.event_ids()
