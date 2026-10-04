from dataclasses import dataclass

from core.equivocation import EquivocationProof


@dataclass(frozen=True)
class EquivocationState:
    """
    Explicit state containing verified equivocation proofs.

    No alternative is selected as a winner.
    """

    proofs: tuple[EquivocationProof, ...]

    def add(
        self,
        proof: EquivocationProof,
    ) -> "EquivocationState":
        if proof in self.proofs:
            return self

        return EquivocationState(
            proofs=self.proofs + (proof,),
        )

    def contains(
        self,
        proof: EquivocationProof,
    ) -> bool:
        return proof in self.proofs

    def is_empty(self) -> bool:
        return not self.proofs

    def has_winner(self) -> bool:
        return False
