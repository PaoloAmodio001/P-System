from dataclasses import dataclass

from core.state import State
from core.event import Transfer
from core.derive import StateDeriver


@dataclass(frozen=True)
class StateProof:
    state_root: str
    events: tuple[Transfer, ...]

    def verify(self, initial_state: State) -> bool:
        try:
            state = StateDeriver.apply_events(
                initial_state,
                list(self.events),
            )
        except ValueError:
            return False

        return state.root() == self.state_root
