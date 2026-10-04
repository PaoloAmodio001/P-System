from dataclasses import dataclass

from core.state import State
from core.event import Transfer
from core.state_proof import StateProof
from core.resolver import ConflictResolver


@dataclass(frozen=True)
class GlobalStateProof:
    state_root: str
    events: tuple[Transfer, ...]
    witnesses: frozenset[str]

    def verify(self, initial_state: State) -> bool:
        if not self.witnesses:
            return False

        if not ConflictResolver.compatible(list(self.events)):
            return False

        proof = StateProof(
            state_root=self.state_root,
            events=self.events,
        )

        return proof.verify(initial_state)
