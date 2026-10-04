from dataclasses import dataclass

from core.relevance import RelevanceNode, RelevanceRegion
from core.relevance_graph import RelevanceGraph


@dataclass(frozen=True)
class ImpactClosure:
    """
    Set of nodes that may affect a decision.

    The closure is derived from an initial relevance region and
    the known relevance graph.

    It does not claim global completeness.
    It only describes the currently modeled impact domain.
    """

    nodes: frozenset[RelevanceNode]

    def contains(self, node: RelevanceNode) -> bool:
        return node in self.nodes

    def keys(self) -> frozenset[str]:
        return frozenset(
            node.key()
            for node in self.nodes
        )

    def intersects(
        self,
        nodes: frozenset[RelevanceNode] | set[RelevanceNode],
    ) -> bool:
        return bool(
            self.nodes.intersection(nodes)
        )

    def is_empty(self) -> bool:
        return not self.nodes


def build_impact_closure(
    region: RelevanceRegion,
    graph: RelevanceGraph,
) -> ImpactClosure:
    """
    Calculate the transitive impact closure of a relevance region.

    Only nodes already represented by the relevance region can be
    materialized as RelevanceNode objects. The graph may therefore
    identify additional keys that are not yet known locally; those
    remain outside the concrete node set.
    """

    closure_keys = graph.closure(
        frozenset(
            node.key()
            for node in region.nodes
        )
    )

    known_nodes = {
        node.key(): node
        for node in region.nodes
    }

    nodes = {
        known_nodes[key]
        for key in closure_keys
        if key in known_nodes
    }

    return ImpactClosure(
        nodes=frozenset(nodes)
    )
