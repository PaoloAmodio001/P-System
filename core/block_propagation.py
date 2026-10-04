from core.event import Transfer
from core.dependency_graph import DependencyGraph


def propagate_blocked(
    events: list[Transfer],
    blocked: set[str],
) -> set[str]:
    """
    Propaga il blocco lungo le dipendenze causali.

    Se un evento è bloccato, ogni suo discendente
    causale viene bloccato a sua volta.
    """

    graph = DependencyGraph.build(events)

    result = set(blocked)

    changed = True

    while changed:
        changed = False

        for event_id, parents in graph.dependencies.items():
            if event_id in result:
                continue

            if parents & result:
                result.add(event_id)
                changed = True

    return result
