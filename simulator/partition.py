from dataclasses import dataclass

from core.event import Transfer
from core.partial_knowledge import PartialKnowledge


@dataclass
class NetworkPartition:
    nodes: dict[str, PartialKnowledge]

    def isolate(
        self,
        node_id: str,
    ) -> None:
        if node_id not in self.nodes:
            raise KeyError(node_id)

        self.nodes[node_id] = PartialKnowledge(
            events=self.nodes[node_id].events
        )

    def add_event(
        self,
        node_id: str,
        event: Transfer,
    ) -> None:
        if node_id not in self.nodes:
            raise KeyError(node_id)

        knowledge = self.nodes[node_id]

        self.nodes[node_id] = PartialKnowledge(
            events=knowledge.events | {event}
        )

    def knowledge(
        self,
        node_id: str,
    ) -> PartialKnowledge:
        if node_id not in self.nodes:
            raise KeyError(node_id)

        return self.nodes[node_id]

    def reconcile(
        self,
        first_node: str,
        second_node: str,
    ) -> None:
        first = self.knowledge(first_node)
        second = self.knowledge(second_node)

        merged = first.merge(second)

        self.nodes[first_node] = merged
        self.nodes[second_node] = merged
