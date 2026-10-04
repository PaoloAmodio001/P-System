from dataclasses import dataclass, field
from hashlib import sha256
import json


@dataclass(frozen=True)
class Transfer:
    sender: str
    receiver: str
    amount: int
    nonce: int
    parents: tuple[str, ...] = field(default_factory=tuple)

    def canonical(self) -> bytes:
        data = {
            "sender": self.sender,
            "receiver": self.receiver,
            "amount": self.amount,
            "nonce": self.nonce,
            "parents": sorted(self.parents),
        }

        return json.dumps(
            data,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()

    def event_id(self) -> str:
        return sha256(self.canonical()).hexdigest()
