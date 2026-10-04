"""Convergence comparison helpers independent of network transport."""
def canonical_projection(node):
    return (
        node.state_root(),
        tuple(event.event_id() for event in node.local_events),
        tuple(sorted(event.event_id() for event in node.events)),
    )


def converged(first, second):
    return canonical_projection(first) == canonical_projection(second)
