"""Small independent reference model.

This model deliberately avoids X-System's StateDeriver, ConflictResolver and
DecisionEngine.  It is intended for differential checking on finite traces.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RefEvent:
    event_id: str
    sender: str
    receiver: str
    amount: int
    nonce: int
    parents: tuple[str, ...] = ()


@dataclass
class ReferenceModel:
    balances: dict[str, int] = field(default_factory=dict)
    nonces: dict[str, int] = field(default_factory=dict)
    events: dict[str, RefEvent] = field(default_factory=dict)
    executed: list[str] = field(default_factory=list)

    def conflict(self, first: RefEvent, second: RefEvent) -> bool:
        return (
            first.sender == second.sender
            and first.nonce == second.nonce
            and first.event_id != second.event_id
        )

    def add(self, event: RefEvent) -> bool:
        if event.event_id in self.events:
            return False
        if any(self.conflict(event, existing) for existing in self.events.values()):
            self.events[event.event_id] = event
            return False
        if any(parent not in self.executed for parent in event.parents):
            return False
        if self.balances.get(event.sender, 0) < event.amount:
            return False
        expected_nonce = self.nonces.get(event.sender, 0)
        if event.nonce != expected_nonce:
            return False
        self.balances[event.sender] = self.balances.get(event.sender, 0) - event.amount
        self.balances[event.receiver] = self.balances.get(event.receiver, 0) + event.amount
        self.nonces[event.sender] = expected_nonce + 1
        self.events[event.event_id] = event
        self.executed.append(event.event_id)
        return True

    def snapshot(self) -> tuple:
        return (
            tuple(sorted(self.balances.items())),
            tuple(sorted(self.nonces.items())),
            tuple(self.executed),
            tuple(sorted(self.events)),
        )
