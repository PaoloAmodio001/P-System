from dataclasses import dataclass

from core.signed_event import SignedTransfer


@dataclass(frozen=True)
class EquivocationProof:
    first: SignedTransfer
    second: SignedTransfer

    def verify(self) -> bool:
        # Entrambe le firme devono essere valide.
        if not self.first.verify():
            return False

        if not self.second.verify():
            return False

        # Deve essere la stessa identità.
        if self.first.public_key != self.second.public_key:
            return False

        first_tx = self.first.transfer
        second_tx = self.second.transfer

        # Le transazioni devono riferirsi allo stesso
        # sender e allo stesso nonce.
        if first_tx.sender != second_tx.sender:
            return False

        if first_tx.nonce != second_tx.nonce:
            return False

        # Devono essere realmente differenti.
        if first_tx == second_tx:
            return False

        return True
