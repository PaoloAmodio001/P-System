from dataclasses import dataclass

from core.event import Transfer


@dataclass(frozen=True)
class GlobalDomain:
    event_ids: frozenset[str]

    def contains(self, event_id: str) -> bool:
        return event_id in self.event_ids

    def covers(self, events: list[Transfer]) -> bool:
        return frozenset(
            event.event_id()
            for event in events
        ) == self.event_ids


def build_global_domain(
    events: list[Transfer],
) -> GlobalDomain:
    return GlobalDomain(
        event_ids=frozenset(
            event.event_id()
            for event in events
        )
    )
