from dataclasses import dataclass

from core.conflict_state import ConflictState
from core.state import State


@dataclass(frozen=True)
class StateView:
    state: State | None = None
    conflict: ConflictState | None = None

    @classmethod
    def unique(cls, state: State) -> "StateView":
        return cls(state=state)

    @classmethod
    def ambiguous(
        cls,
        conflict: ConflictState,
    ) -> "StateView":
        return cls(conflict=conflict)

    def is_unique(self) -> bool:
        return (
            self.state is not None
            and self.conflict is None
        )

    def is_ambiguous(self) -> bool:
        return (
            self.state is None
            and self.conflict is not None
        )

    def has_winner(self) -> bool:
        return False

    def alternatives(self):
        if self.conflict is None:
            return ()

        return self.conflict.alternatives
