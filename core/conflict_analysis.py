from dataclasses import dataclass

from core.conflict_set import ConflictSet


@dataclass(frozen=True)
class ConflictAnalysis:
    valid_candidates: tuple[str, ...]
    conflicting: bool
    winner: None = None

    @property
    def has_winner(self) -> bool:
        return self.winner is not None


def analyze(
    conflict_set: ConflictSet,
    initial_state,
) -> ConflictAnalysis:

    valid = conflict_set.valid_candidates(initial_state)

    return ConflictAnalysis(
        valid_candidates=valid,
        conflicting=len(valid) > 1,
    )
