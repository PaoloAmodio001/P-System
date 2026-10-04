from dataclasses import dataclass

from core.event import Transfer
from core.incompatibility import incompatible
from core.partial_knowledge import PartialKnowledge


@dataclass(frozen=True)
class ReconciliationConflict:
    first: Transfer
    second: Transfer

    def is_conflict(self) -> bool:
        return incompatible(
            self.first,
            self.second,
        )


def find_conflicts(
    first: PartialKnowledge,
    second: PartialKnowledge,
) -> tuple[ReconciliationConflict, ...]:

    events_a = list(first.events)
    events_b = list(second.events)

    conflicts = []

    for event_a in events_a:
        for event_b in events_b:
            if incompatible(event_a, event_b):
                conflicts.append(
                    ReconciliationConflict(
                        first=event_a,
                        second=event_b,
                    )
                )

    return tuple(conflicts)
