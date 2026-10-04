from core.relevance import RelevanceNode, RelevanceRegion
from core.relevance_graph import RelevanceGraph


def build_relevance_closure(
    region: RelevanceRegion,
    graph: RelevanceGraph,
) -> frozenset[RelevanceNode]:
    """
    Espande la regione iniziale seguendo tutte le dipendenze
    rappresentate dal RelevanceGraph.
    """

    node_by_key = {
        node.key(): node
        for node in region.nodes
    }

    roots = {
        node.key()
        for node in region.nodes
    }

    closure_keys = graph.closure(roots)

    result = set(region.nodes)

    for key in closure_keys:
        node = node_by_key.get(key)

        if node is not None:
            result.add(node)

    return frozenset(result)
