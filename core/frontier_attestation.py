from dataclasses import dataclass

from core.event import Transfer


@dataclass(frozen=True)
class FrontierAttestation:
    observer: str
    event_ids: frozenset[str]

    def covers(self, events: list[Transfer]) -> bool:
        return frozenset(
            event.event_id()
            for event in events
        ) == self.event_ids


def create_attestation(
    observer: str,
    events: list[Transfer],
) -> FrontierAttestation:
    return FrontierAttestation(
        observer=observer,
        event_ids=frozenset(
            event.event_id()
            for event in events
        ),
    )
