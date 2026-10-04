from core.event import Transfer
from core.dependency_graph import DependencyGraph


def depends_on(
    event: Transfer,
    ancestor_id: str,
    events: list[Transfer],
    graph: DependencyGraph | None = None,
) -> bool:
    if graph is None:
        graph = DependencyGraph.build(events)

    if event.event_id() not in graph.dependencies:
        return False

    visited = set()
    stack = list(graph.parents_of(event.event_id()))

    while stack:
        current = stack.pop()

        if current == ancestor_id:
            return True

        if current in visited:
            continue

        visited.add(current)
        stack.extend(graph.parents_of(current))

    return False
