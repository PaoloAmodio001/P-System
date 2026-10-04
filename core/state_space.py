from dataclasses import dataclass

from core.conflict_set import ConflictCandidate
from core.state import State


@dataclass(frozen=True)
class StateRelation:
    first: str
    second: str
    relation: str


@dataclass(frozen=True)
class StateSpace:
    candidates: tuple[ConflictCandidate, ...]

    def names(self) -> tuple[str, ...]:
        return tuple(
            candidate.name
            for candidate in self.candidates
        )

    def relations(self) -> tuple[StateRelation, ...]:
        result = []

        for i, first in enumerate(self.candidates):
            for second in self.candidates[i + 1:]:
                if (
                    first.state_root == second.state_root
                ):
                    relation = "EQUIVALENT"
                else:
                    relation = "DISTINCT"

                result.append(
                    StateRelation(
                        first=first.name,
                        second=second.name,
                        relation=relation,
                    )
                )

        return tuple(result)

    def valid(
        self,
        initial_state: State,
    ) -> tuple[str, ...]:
        return tuple(
            candidate.name
            for candidate in self.candidates
            if candidate.verify(initial_state)
        )

    def contains_multiple_valid_states(
        self,
        initial_state: State,
    ) -> bool:
        return len(self.valid(initial_state)) > 1
