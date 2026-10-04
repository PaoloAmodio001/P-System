from dataclasses import dataclass

from core.event import Transfer
from core.incompatibility import incompatible


@dataclass(frozen=True)
class ConflictState:
    alternatives: tuple[Transfer, ...]

    def add(self, event: Transfer) -> "ConflictState":
        if event in self.alternatives:
            return self

        return ConflictState(
            alternatives=self.alternatives + (event,),
        )

    def is_conflicted(self) -> bool:
        for i, first in enumerate(self.alternatives):
            for second in self.alternatives[i + 1:]:
                if incompatible(first, second):
                    return True

        return False

    def has_winner(self) -> bool:
        return False

    def contains(self, event: Transfer) -> bool:
        return event in self.alternatives
