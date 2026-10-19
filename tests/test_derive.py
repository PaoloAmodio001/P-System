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


def test_topological_order_rejects_missing_parent():
    event = Transfer(
        "alice",
        "bob",
        3,
        0,
        parents=("0" * 64,),
    )

    try:
        StateDeriver._topological_order([event])
    except ValueError as error:
        assert "UNKNOWN PARENT" in str(error)
    else:
        raise AssertionError("MISSING PARENT WAS ACCEPTED")


def test_apply_events_rejects_missing_parent():
    initial = State({"alice": 10, "bob": 0})
    event = Transfer(
        "alice",
        "bob",
        3,
        0,
        parents=("0" * 64,),
    )

    try:
        StateDeriver.apply_events(initial, [event])
    except ValueError as error:
        assert "UNKNOWN PARENT" in str(error)
    else:
        raise AssertionError("MISSING PARENT WAS ACCEPTED")


def test_topological_order_deduplicates_identical_events():
    event = Transfer("alice", "bob", 3, 0)

    ordered = StateDeriver._topological_order([event, event])

    assert len(ordered) == 1
    assert ordered[0] == event
    assert ordered[0].event_id() == event.event_id()


def test_topological_order_parent_precedes_child_for_permutations():
    from itertools import permutations

    first = Transfer("alice", "bob", 4, 0)
    second = Transfer(
        "bob", "carol", 3, 0,
        parents=(first.event_id(),),
    )
    third = Transfer(
        "carol", "dave", 2, 0,
        parents=(second.event_id(),),
    )
    events = [first, second, third]

    for permutation in permutations(events):
        ordered = StateDeriver._topological_order(list(permutation))
        ids = [event.event_id() for event in ordered]
        assert len(ids) == len(set(ids)) == 3
        assert ids.index(first.event_id()) < ids.index(second.event_id())
        assert ids.index(second.event_id()) < ids.index(third.event_id())
        assert ids.index(first.event_id()) < ids.index(third.event_id())


def test_topological_order_independent_events_is_deterministic():
    events = [
        Transfer("alice", "bob", 1, 0),
        Transfer("carol", "dave", 2, 0),
        Transfer("eve", "frank", 3, 0),
    ]

    expected = sorted(event.event_id() for event in events)

    for permutation in __import__("itertools").permutations(events):
        ordered = StateDeriver._topological_order(list(permutation))
        assert [event.event_id() for event in ordered] == expected



def test_topological_order_rejects_cycle():
    class FixedIdEvent:
        def __init__(self, identifier, parents):
            self.identifier = identifier
            self.parents = parents

        def event_id(self):
            return self.identifier

    first = FixedIdEvent("first", ("second",))
    second = FixedIdEvent("second", ("first",))

    try:
        StateDeriver._topological_order([first, second])
    except ValueError as error:
        assert str(error) == "CYCLIC EVENT DEPENDENCY"
    else:
        raise AssertionError("CYCLIC DEPENDENCY WAS ACCEPTED")


def test_deduplicate_events_keeps_identical_duplicates_once():
    from core.event import deduplicate_events, Transfer

    event = Transfer("alice", "bob", 3, 0)
    result = deduplicate_events([event, event])

    assert result == [event]


def test_deduplicate_events_rejects_same_id_different_content():
    import pytest
    from core.event import deduplicate_events

    class FixedIdEvent:
        def __init__(self, identifier, amount):
            self.identifier = identifier
            self.sender = "alice"
            self.receiver = "bob"
            self.amount = amount
            self.nonce = 0
            self.parents = ()

        def event_id(self):
            return self.identifier

        def canonical(self):
            return str(self.amount).encode()

    first = FixedIdEvent("same-id", 3)
    second = FixedIdEvent("same-id", 4)

    with pytest.raises(
        ValueError,
        match="DUPLICATE EVENT ID WITH DIFFERENT CONTENT",
    ):
        deduplicate_events([first, second])
