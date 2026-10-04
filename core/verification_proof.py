from dataclasses import dataclass

from core.event import Transfer
from core.causal_closure import verify_causal_closure
from core.dependency_closure import verify_dependency_closure
from core.conflict_closure import find_conflicts


@dataclass(frozen=True)
class VerificationProof:
    event_ids: frozenset[str]
    conflict_count: int

    @classmethod
    def create(
        cls,
        events: list[Transfer],
    ) -> "VerificationProof":

        event_ids = frozenset(
            event.event_id()
            for event in events
        )

        conflicts = find_conflicts(events)

        return cls(
            event_ids=event_ids,
            conflict_count=len(conflicts),
        )

    def verify(
        self,
        events: list[Transfer],
    ) -> bool:

        actual_ids = frozenset(
            event.event_id()
            for event in events
        )

        if actual_ids != self.event_ids:
            return False

        if not verify_causal_closure(events):
            return False

        if not verify_dependency_closure(events):
            return False

        actual_conflicts = find_conflicts(events)

        if len(actual_conflicts) != self.conflict_count:
            return False

        return True
