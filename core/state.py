from dataclasses import dataclass, field
from hashlib import sha256
import json


@dataclass
class State:
    balances: dict[str, int] = field(default_factory=dict)
    nonces: dict[str, int] = field(default_factory=dict)

    def copy(self):
        return State(
            balances=self.balances.copy(),
            nonces=self.nonces.copy(),
        )

    def canonical(self) -> bytes:
        data = {
            "balances": dict(sorted(self.balances.items())),
            "nonces": dict(sorted(self.nonces.items())),
        }

        return json.dumps(
            data,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()

    def root(self) -> str:
        return sha256(self.canonical()).hexdigest()

    def balance(self, identity: str) -> int:
        return self.balances.get(identity, 0)

    def nonce(self, identity: str) -> int:
        return self.nonces.get(identity, 0)
