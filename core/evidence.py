from dataclasses import dataclass

from core.signed_event import SignedTransfer


@dataclass(frozen=True)
class Evidence:
    event: SignedTransfer
    observed_by: frozenset[str]

    def valid(self) -> bool:
        return self.event.verify()

    def strength(self) -> int:
        return len(self.observed_by)
