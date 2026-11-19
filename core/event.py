from dataclasses import dataclass, field
from hashlib import sha256
import json

# Structured data carried by an event (docs/MISSION-RECORDS.md). The bound keeps a certificate,
# which repeats its event, far below the limits of a frame and of an API body.
MAX_DATA_BYTES = 16 * 1024


def canonical_data(value: dict) -> str:
    """The one text of a JSON object that an event can carry: sorted keys, no spaces, ASCII."""
    if type(value) is not dict:
        raise ValueError("EVENT DATA IS A JSON OBJECT")

    text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)

    if len(text.encode()) > MAX_DATA_BYTES:
        raise ValueError(f"EVENT DATA OVER {MAX_DATA_BYTES} BYTES")

    return text


def is_canonical_data(data) -> bool:
    """
    Whether `data` can be the data of an event: empty, or the canonical text of a JSON object.

    One value has one text, so that the event id, which hashes the text, is a function of the value.
    This never raises.
    """
    if type(data) is not str:
        return False

    if data == "":
        return True

    if len(data) > MAX_DATA_BYTES:
        return False

    try:
        value = json.loads(data)
        return type(value) is dict and canonical_data(value) == data
    except (ValueError, RecursionError):
        return False


@dataclass(frozen=True)
class Transfer:
    sender: str
    receiver: str
    amount: int
    nonce: int
    parents: tuple[str, ...] = field(default_factory=tuple)
    # Canonical JSON of an object, or empty. Empty leaves the canonical form, and so the id and the
    # signature, exactly as they were before data existed.
    data: str = ""

    def canonical(self) -> bytes:
        data = {
            "sender": self.sender,
            "receiver": self.receiver,
            "amount": self.amount,
            "nonce": self.nonce,
            "parents": sorted(self.parents),
        }

        if self.data != "":
            data["data"] = self.data

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
    fields = ("sender", "receiver", "amount", "nonce", "parents", "data")
    return repr(tuple((name, getattr(event, name, None)) for name in fields)).encode()


def transfer_from_canonical_dict(data: dict) -> Transfer:
    """The event of a decoded canonical form, as the store and the wallet keep it."""
    return Transfer(
        sender=data["sender"],
        receiver=data["receiver"],
        amount=data["amount"],
        nonce=data["nonce"],
        parents=tuple(data["parents"]),
        data=data.get("data", ""),
    )


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
