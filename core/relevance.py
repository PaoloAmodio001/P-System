from dataclasses import dataclass

from core.event import Transfer
from core.state import State


@dataclass(frozen=True)
class RelevanceNode:
    kind: str
    identifier: str

    def key(self) -> str:
        return f"{self.kind}:{self.identifier}"


@dataclass(frozen=True)
class RelevanceRegion:
    nodes: frozenset[RelevanceNode]

    def contains(self, node: RelevanceNode) -> bool:
        return node in self.nodes


def transfer_nodes(event: Transfer) -> frozenset[RelevanceNode]:
    return frozenset(
        {
            RelevanceNode("balance", event.sender),
            RelevanceNode("balance", event.receiver),
            RelevanceNode("nonce", event.sender),
            RelevanceNode("event", event.event_id()),
        }
    )


def build_relevance_region(
    state: State,
    events: list[Transfer],
) -> RelevanceRegion:
    nodes: set[RelevanceNode] = set()

    for event in events:
        nodes.update(
            transfer_nodes(event)
        )

    return RelevanceRegion(
        nodes=frozenset(nodes)
    )
