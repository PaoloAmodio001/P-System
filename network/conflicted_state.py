from dataclasses import dataclass

from core.conflict_state import ConflictState
from core.event import Transfer
from core.state import State


@dataclass(frozen=True)
class ConflictedState:
    base_state: State
    alternatives: ConflictState

    @property
    def is_conflicted(self) -> bool:
        return self.alternatives.is_conflicted()

    @property
    def has_winner(self) -> bool:
        return False

    def contains(self, event: Transfer) -> bool:
        return self.alternatives.contains(event)
