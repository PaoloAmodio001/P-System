from dataclasses import dataclass

from core.state import State
from core.event import Transfer


@dataclass(frozen=True)
class Conflict:
    state_a: State
    tx_a: Transfer
    state_b: State
    tx_b: Transfer

    def is_double_spend(self) -> bool:
        return (
            self.tx_a.sender == self.tx_b.sender
            and self.tx_a.nonce == self.tx_b.nonce
            and self.tx_a != self.tx_b
        )

    def roots(self) -> tuple[str, str]:
        return (
            self.state_a.root(),
            self.state_b.root(),
        )

    def describe(self) -> dict:
        return {
            "type": "DOUBLE_SPEND",
            "sender": self.tx_a.sender,
            "nonce": self.tx_a.nonce,
            "transaction_a": {
                "receiver": self.tx_a.receiver,
                "amount": self.tx_a.amount,
            },
            "transaction_b": {
                "receiver": self.tx_b.receiver,
                "amount": self.tx_b.amount,
            },
            "state_root_a": self.state_a.root(),
            "state_root_b": self.state_b.root(),
        }
