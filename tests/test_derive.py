from core.state import State
from core.event import Transfer
from core.derive import StateDeriver


def test_deterministic_state():

    initial = State({
        "alice": 10,
        "bob": 0,
        "carol": 0,
    })

    events = [
        Transfer("alice", "bob", 3, 0),
        Transfer("alice", "carol", 2, 1),
    ]

    state_a = StateDeriver.apply_events(
        initial,
        events,
    )

    state_b = StateDeriver.apply_events(
        initial,
        list(reversed(events)),
    )

    assert state_a.root() == state_b.root()

    assert state_a.balance("alice") == 5
    assert state_a.balance("bob") == 3
    assert state_a.balance("carol") == 2


def test_conflicting_events_rejected():

    initial = State({
        "alice": 10,
        "bob": 0,
        "carol": 0,
    })

    events = [
        Transfer("alice", "bob", 8, 0),
        Transfer("alice", "carol", 8, 0),
    ]

    try:
        StateDeriver.apply_events(initial, events)
        assert False
    except ValueError as error:
        assert str(error) == "CONFLICTING EVENTS"


def test_topological_order_parent_precedes_child():
    parent = Transfer("alice", "bob", 4, 0)
    child = Transfer(
        "bob",
        "carol",
        2,
        0,
        parents=(parent.event_id(),),
    )

    ordered = StateDeriver._topological_order([child, parent])
    ids = [event.event_id() for event in ordered]

    assert ids.index(parent.event_id()) < ids.index(child.event_id())


def test_topological_order_transitive_causality():
    first = Transfer("alice", "bob", 4, 0)
    second = Transfer(
        "bob",
        "carol",
        3,
        0,
        parents=(first.event_id(),),
    )
    third = Transfer(
        "carol",
        "dave",
        2,
        0,
        parents=(second.event_id(),),
    )

    ordered = StateDeriver._topological_order([third, first, second])
    ids = [event.event_id() for event in ordered]

    assert ids.index(first.event_id()) < ids.index(second.event_id())
    assert ids.index(second.event_id()) < ids.index(third.event_id())
    assert ids.index(first.event_id()) < ids.index(third.event_id())


def test_topological_order_all_parents_precede_child():
    first = Transfer("alice", "bob", 4, 0)
    second = Transfer("carol", "dave", 3, 0)
    child = Transfer(
        "bob",
        "eve",
        2,
        1,
        parents=(first.event_id(), second.event_id()),
    )

    ordered = StateDeriver._topological_order([child, second, first])
    ids = [event.event_id() for event in ordered]
    child_position = ids.index(child.event_id())

    assert ids.index(first.event_id()) < child_position
    assert ids.index(second.event_id()) < child_position
