from dataclasses import dataclass
from core.state import State
from core.event import Transfer
from core.state_proof import StateProof


@dataclass(frozen=True)
class ConflictCandidate:
    name: str
    state_root: str
    events: tuple[Transfer, ...]

    def verify(self, initial_state: State) -> bool:
        proof = StateProof(
            state_root=self.state_root,
            events=self.events,
        )
        return proof.verify(initial_state)


@dataclass(frozen=True)
class ConflictSet:
    candidates: tuple[ConflictCandidate, ...]

    def valid_candidates(self, initial_state: State) -> tuple[str, ...]:
        return tuple(
            candidate.name
            for candidate in self.candidates
            if candidate.verify(initial_state)
        )

    def has_conflict(self, initial_state: State) -> bool:
        valid = self.valid_candidates(initial_state)
        return len(valid) > 1
