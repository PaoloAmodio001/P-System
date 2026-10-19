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


def event_payload(event) -> bytes:
    canonical = getattr(event, "canonical", None)
    if callable(canonical):
        return canonical()
    fields = ("sender", "receiver", "amount", "nonce", "parents")
    return repr(tuple((name, getattr(event, name, None)) for name in fields)).encode()


def deduplicate_events(events):
    by_id = {}
    payloads = {}
    for event in events:
        event_id = event.event_id()
        payload = event_payload(event)
        if event_id in by_id:
            if payloads[event_id] != payload:
                raise ValueError("DUPLICATE EVENT ID WITH DIFFERENT CONTENT")
            continue
        by_id[event_id] = event
        payloads[event_id] = payload
    return list(by_id.values())
