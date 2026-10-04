from dataclasses import dataclass

from core.event import Transfer
from core.state import State
from core.verification_proof import VerificationProof
from core.state_proof import StateProof


@dataclass(frozen=True)
class VerifiableState:
    state_root: str
    proof: VerificationProof

    @classmethod
    def create(
        cls,
        initial_state: State,
        events: list[Transfer],
    ) -> "VerifiableState":

        verification = VerificationProof.create(
            events
        )

        from core.derive import StateDeriver

        state = StateDeriver.apply_events(
            initial_state,
            events,
        )

        return cls(
            state_root=state.root(),
            proof=verification,
        )

    def verify(
        self,
        initial_state: State,
        events: list[Transfer],
    ) -> bool:

        if not self.proof.verify(events):
            return False

        state_proof = StateProof(
            state_root=self.state_root,
            events=tuple(events),
        )

        return state_proof.verify(
            initial_state
        )
