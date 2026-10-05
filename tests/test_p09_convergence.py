from itertools import permutations

from core.derive import StateDeriver
from core.event import Transfer
from core.state import State


def _state_root(events):
    initial = State({
        "alice": 20,
        "bob": 20,
        "carol": 20,
        "dave": 0,
    })
    return StateDeriver.apply_events(initial, list(events)).root()


def test_p09_independent_events_converge_across_all_permutations():
    events = (
        Transfer("alice", "bob", 2, 0),
        Transfer("alice", "carol", 3, 1),
        Transfer("bob", "dave", 1, 0),
        Transfer("carol", "dave", 1, 0),
    )

    roots = {
        _state_root(order)
        for order in permutations(events)
    }

    assert len(roots) == 1


def test_p09_causal_chain_converges_across_all_permutations():
    events = (
        Transfer("alice", "bob", 2, 0),
        Transfer("bob", "carol", 1, 0, parents=(
            Transfer("alice", "bob", 2, 0).event_id(),
        )),
        Transfer("carol", "dave", 1, 0, parents=(
            Transfer(
                "bob",
                "carol",
                1,
                0,
                parents=(Transfer("alice", "bob", 2, 0).event_id(),),
            ).event_id(),
        )),
    )

    roots = {
        _state_root(order)
        for order in permutations(events)
    }

    assert len(roots) == 1


def test_p09_mixed_independent_and_causal_events_converge():
    root_event = Transfer("alice", "bob", 2, 0)
    child_event = Transfer(
        "bob",
        "carol",
        1,
        0,
        parents=(root_event.event_id(),),
    )
    independent = Transfer("carol", "dave", 1, 0)

    events = (
        root_event,
        child_event,
        independent,
    )

    roots = {
        _state_root(order)
        for order in permutations(events)
    }

    assert len(roots) == 1


def test_p09_conflicting_knowledge_converges_without_order_dependent_winner():
    from core.resolver import ConflictResolver
    from core.event import Transfer

    first = Transfer("alice", "bob", 2, 0)
    conflicting = Transfer("alice", "carol", 3, 0)

    assert ConflictResolver.conflicting(first, conflicting)

    # Same conflicting knowledge, delivered in opposite orders.
    # The projection must not select one alternative merely because
    # it arrived first.
    def projection(order):
        try:
            _state_root(order)
        except ValueError:
            return "CONFLICTED"

        return "EXECUTABLE"

    assert projection((first, conflicting)) == "CONFLICTED"
    assert projection((conflicting, first)) == "CONFLICTED"
