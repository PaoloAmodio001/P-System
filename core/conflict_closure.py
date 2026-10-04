from dataclasses import dataclass

from core.event import Transfer
from core.incompatibility import incompatible


@dataclass(frozen=True)
class ConflictClosure:
    event_ids: frozenset[str]
    conflicts: tuple[tuple[str, str], ...]

    def contains(self, event_id: str) -> bool:
        return event_id in self.event_ids

    def has_conflicts(self) -> bool:
        return bool(self.conflicts)


def find_conflicts(
    events: list[Transfer],
) -> tuple[tuple[str, str], ...]:
    conflicts = []

    for i, first in enumerate(events):
        for second in events[i + 1:]:
            if incompatible(first, second):
                conflicts.append(
                    (
                        first.event_id(),
                        second.event_id(),
                    )
                )

    return tuple(conflicts)


def build_conflict_closure(
    events: list[Transfer],
) -> ConflictClosure:
    event_ids = frozenset(
        event.event_id()
        for event in events
    )

    conflicts = find_conflicts(events)

    return ConflictClosure(
        event_ids=event_ids,
        conflicts=conflicts,
    )
