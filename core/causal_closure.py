from dataclasses import dataclass

from core.dependency_graph import DependencyGraph
from core.event import Transfer


@dataclass(frozen=True)
class CausalClosure:
    event_ids: frozenset[str]

    def contains(self, event_id: str) -> bool:
        return event_id in self.event_ids


def verify_causal_closure(
    events: list[Transfer],
) -> bool:
    try:
        graph = DependencyGraph.build(events)
    except ValueError:
        return False

    if graph.has_cycle():
        return False

    known_ids = {
        event.event_id()
        for event in events
    }

    for event in events:
        if not set(event.parents).issubset(known_ids):
            return False

    return True


def build_causal_closure(
    events: list[Transfer],
) -> CausalClosure | None:
    if not verify_causal_closure(events):
        return None

    return CausalClosure(
        event_ids=frozenset(
            event.event_id()
            for event in events
        )
    )
