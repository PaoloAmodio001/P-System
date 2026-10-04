from dataclasses import dataclass
from enum import Enum

from core.relevance_graph import RelevanceGraph


class RelevanceStatus(Enum):
    KNOWN = "KNOWN"
    IRRELEVANT = "IRRELEVANT"
    POTENTIALLY_RELEVANT = "POTENTIALLY_RELEVANT"


@dataclass(frozen=True)
class UncertaintyBoundary:
    known: frozenset[str]
    potentially_relevant: frozenset[str]
    irrelevant: frozenset[str]

    def status(self, node: str) -> RelevanceStatus:
        if node in self.potentially_relevant:
            return RelevanceStatus.POTENTIALLY_RELEVANT

        if node in self.known:
            return RelevanceStatus.KNOWN

        return RelevanceStatus.IRRELEVANT


def analyze_boundary(
    known: set[str] | frozenset[str],
    graph: RelevanceGraph,
) -> UncertaintyBoundary:
    known_set = set(known)
    potentially_relevant = set()

    # Seguiamo ricorsivamente tutta la regione raggiungibile
    # dalle informazioni conosciute.
    stack = list(known_set)
    visited = set(known_set)

    while stack:
        current = stack.pop()

        for target in graph.successors(current):
            if target in visited:
                continue

            visited.add(target)
            potentially_relevant.add(target)
            stack.append(target)

    potentially_relevant.difference_update(
        known_set
    )

    all_nodes = set(graph.edges)

    for targets in graph.edges.values():
        all_nodes.update(targets)

    irrelevant = (
        all_nodes
        - known_set
        - potentially_relevant
    )

    return UncertaintyBoundary(
        known=frozenset(known_set),
        potentially_relevant=frozenset(
            potentially_relevant
        ),
        irrelevant=frozenset(irrelevant),
    )
