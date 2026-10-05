from itertools import permutations

from core.derive import StateDeriver
from core.event import Transfer
from core.state import State


def _root(events):
    initial = State({
        "alice": 20,
        "bob": 20,
        "carol": 20,
        "dave": 20,
        "eve": 20,
    })
    return StateDeriver.apply_events(initial, list(events)).root()


def test_p09_causal_branch_convergence():
    root = Transfer("alice", "bob", 2, 0)

    left = Transfer(
        "bob",
        "carol",
        1,
        0,
        parents=(root.event_id(),),
    )

    right = Transfer(
        "dave",
        "eve",
        1,
        0,
        parents=(root.event_id(),),
    )

    merge = Transfer(
        "carol",
        "dave",
        1,
        0,
        parents=(left.event_id(), right.event_id()),
    )

    events = (root, left, right, merge)

    roots = {
        _root(order)
        for order in permutations(events)
    }

    assert len(roots) == 1
