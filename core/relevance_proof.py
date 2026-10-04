from dataclasses import dataclass

from core.event import Transfer
from core.state import State
from core.proof import apply_transfer


@dataclass(frozen=True)
class RelevanceProof:
    state_root: str
    relevant_event_ids: frozenset[str]

    def verify(
        self,
        state: State,
        events: list[Transfer],
    ) -> bool:
        if state.root() != self.state_root:
            return False

        known_ids = frozenset(
            event.event_id()
            for event in events
        )

        if not self.relevant_event_ids.issubset(
            known_ids
        ):
            return False

        return True


def build_relevance_proof(
    state: State,
    events: list[Transfer],
) -> RelevanceProof:

    relevant = []

    for event in events:
        try:
            apply_transfer(
                state,
                event,
            )
        except ValueError:
            continue

        relevant.append(
            event.event_id()
        )

    return RelevanceProof(
        state_root=state.root(),
        relevant_event_ids=frozenset(
            relevant
        ),
    )
