from dataclasses import dataclass

from core.signed_event import SignedTransfer


@dataclass(frozen=True)
class EquivocationProof:
    first: SignedTransfer
    second: SignedTransfer

    def verify(self) -> bool:
        # Both signatures must be valid.
        if not self.first.verify():
            return False

        if not self.second.verify():
            return False

        # It must be the same identity.
        if self.first.public_key != self.second.public_key:
            return False

        first_tx = self.first.transfer
        second_tx = self.second.transfer

        # The transfers must be for the same
        # sender and the same nonce.
        if first_tx.sender != second_tx.sender:
            return False

        if first_tx.nonce != second_tx.nonce:
            return False

        # Devono essere realmente differenti.
        if first_tx.event_id() == second_tx.event_id():
            return False

        return True
