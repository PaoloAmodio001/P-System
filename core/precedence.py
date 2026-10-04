from dataclasses import dataclass
from crypto.identity import Identity, verify_signature


@dataclass(frozen=True)
class PrecedenceAttestation:
    earlier_event: str
    later_event: str
    observer: bytes
    signature: bytes

    @classmethod
    def create(
        cls,
        identity: Identity,
        earlier_event: str,
        later_event: str,
    ):
        if earlier_event == later_event:
            raise ValueError("IDENTICAL EVENTS")

        payload = (
            earlier_event.encode()
            + b":BEFORE:"
            + later_event.encode()
        )

        return cls(
            earlier_event=earlier_event,
            later_event=later_event,
            observer=identity.public_key,
            signature=identity.sign(payload),
        )

    def verify(self) -> bool:
        if self.earlier_event == self.later_event:
            return False

        payload = (
            self.earlier_event.encode()
            + b":BEFORE:"
            + self.later_event.encode()
        )

        return verify_signature(
            self.observer,
            self.signature,
            payload,
        )
