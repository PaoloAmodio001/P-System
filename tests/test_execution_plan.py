from core.event import Transfer
from core.execution_plan import build_execution_plan
from core.state import State


def test_independent_events_are_parallel():
    initial = State({
        "alice": 10,
        "bob": 10,
        "carol": 0,
        "dave": 0,
    })

    first = Transfer("alice", "carol", 5, 0)
    second = Transfer("bob", "dave", 5, 0)

    plan = build_execution_plan(
        initial,
        [first, second],
    )

    assert len(plan.parallel) == 1
    assert not plan.ordered
    assert not plan.conflicts


def test_same_sender_different_nonces_are_ordered():
    initial = State({
        "alice": 10,
        "bob": 0,
        "carol": 0,
    })

    first = Transfer("alice", "bob", 4, 0)
    second = Transfer("alice", "carol", 3, 1)

    plan = build_execution_plan(
        initial,
        [first, second],
    )

    assert not plan.parallel
    assert len(plan.ordered) == 1
    assert not plan.conflicts


def test_double_spend_is_conflict():
    initial = State({
        "alice": 10,
        "bob": 0,
        "carol": 0,
    })

    first = Transfer("alice", "bob", 6, 0)
    second = Transfer("alice", "carol", 7, 0)

    plan = build_execution_plan(
        initial,
        [first, second],
    )

    assert not plan.parallel
    assert not plan.ordered
    assert len(plan.conflicts) == 1
def test_many_independent_events_are_all_parallel():
    initial = State({
        "alice": 10,
        "bob": 10,
        "carol": 10,
        "dave": 10,
        "eve": 0,
        "frank": 0,
        "grace": 0,
        "heidi": 0,
    })

    events = [
        Transfer("alice", "eve", 5, 0),
        Transfer("bob", "frank", 5, 0),
        Transfer("carol", "grace", 5, 0),
        Transfer("dave", "heidi", 5, 0),
    ]

    plan = build_execution_plan(initial, events)

    assert len(plan.parallel) == 6
    assert not plan.ordered
    assert not plan.conflicts
def test_execution_plan_contains_implicit_parallel_execution():
    initial = State({
        "alice": 10,
        "carol": 10,
        "eve": 10,
    })

    events = [
        Transfer("alice", "bob", 5, 0),
        Transfer("carol", "dave", 5, 0),
        Transfer("eve", "frank", 5, 0),
    ]

    plan = build_execution_plan(initial, events)

    assert plan.parallel_execution is not None
    assert plan.parallel_execution.event_ids == tuple(
        event.event_id()
        for event in events
    )

def test_execution_plan_deduplicates_identical_events():
    first = Transfer("alice", "bob", 3, 0)
    plan = build_execution_plan(State(), [first, first])

    assert plan.parallel_execution is not None
    assert plan.parallel_execution.event_ids == (first.event_id(),)
    assert plan.parallel == ()
    assert plan.parallel_event_count == 1
    assert not plan.ordered
    assert not plan.conflicts
