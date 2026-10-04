"""Differential comparison between production projections and the reference model."""
def compare_snapshots(actual, expected):
    if actual == expected:
        return True, None
    return False, {"actual": actual, "expected": expected}


def node_snapshot(node):
    return {
        "balances": tuple(sorted(node.state.balances.items())),
        "nonces": tuple(sorted(node.state.nonces.items())),
        "executed": tuple(event.event_id() for event in node.local_events),
        "known": tuple(sorted(event.event_id() for event in node.events)),
    }
