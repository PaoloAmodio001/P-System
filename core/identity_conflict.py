from dataclasses import dataclass

from core.identity_claim import IdentityClaim


def identity_incompatible(
    first: IdentityClaim,
    second: IdentityClaim,
) -> bool:
    """
    Determine whether two identity claims are incompatible.

    Two claims are incompatible when:
    - they declare the same alias;
    - they refer to different cryptographic identities.

    This does not determine which claim is correct.
    """

    if first.alias != second.alias:
        return False

    return first.identity_id != second.identity_id


@dataclass(frozen=True)
class IdentityConflictState:
    """
    Explicit state for conflicting identity claims.

    No alternative is selected as a winner.
    """

    alternatives: tuple[IdentityClaim, ...]

    def add(
        self,
        claim: IdentityClaim,
    ) -> "IdentityConflictState":
        if claim in self.alternatives:
            return self

        return IdentityConflictState(
            alternatives=self.alternatives + (claim,),
        )

    def is_conflicted(self) -> bool:
        for i, first in enumerate(self.alternatives):
            for second in self.alternatives[i + 1:]:
                if identity_incompatible(first, second):
                    return True

        return False

    def has_winner(self) -> bool:
        return False

    def contains_identity(
        self,
        identity_id: str,
    ) -> bool:
        return any(
            claim.identity_id == identity_id
            for claim in self.alternatives
        )

    def contains(
        self,
        claim: IdentityClaim,
    ) -> bool:
        return claim in self.alternatives
