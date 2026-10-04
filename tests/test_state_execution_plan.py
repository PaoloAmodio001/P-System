from core.event import Transfer
from core.state import State
from core.state_execution_plan import build_state_execution_plan


def test_state_execution_plan_classifies_relationships():
    initial = State(
        balances={
            "alice": 10,
            "bob": 0,
            "carol": 5,
            "dave": 0,
        }
    )

    compatible_a = Transfer("alice", "bob", 3, 0)
    compatible_b = Transfer("carol", "dave", 2, 0)

    ordered_a = Transfer("alice", "bob", 5, 0)
    ordered_b = Transfer("bob", "carol", 2, 0)

    conflict_a = Transfer("alice", "bob", 5, 1)
    conflict_b = Transfer("alice", "dave", 4, 1)

    events = [
        compatible_a,
        compatible_b,
        ordered_a,
        ordered_b,
        conflict_a,
        conflict_b,
    ]

    plan = build_state_execution_plan(
        initial,
        events,
    )

    assert plan.parallel
    assert plan.ordered
    assert plan.conflicts
    assert plan.has_conflicts()


def test_state_execution_plan_empty_for_no_events():
    initial = State()

    plan = build_state_execution_plan(
        initial,
        [],
    )

    assert plan.parallel == ()
    assert plan.ordered == ()
    assert plan.conflicts == ()
    assert not plan.has_conflicts()


def test_each_pair_belongs_to_only_one_category():
    initial = State(
        balances={
            "alice": 10,
            "bob": 0,
            "carol": 10,
            "dave": 0,
        }
    )

    events = [
        Transfer("alice", "bob", 3, 0),
        Transfer("carol", "dave", 2, 0),
        Transfer("alice", "bob", 5, 1),
    ]

    plan = build_state_execution_plan(
        initial,
        events,
    )

    parallel = set(plan.parallel)
    ordered = set(plan.ordered)
    conflicts = set(plan.conflicts)

    assert parallel.isdisjoint(ordered)
    assert parallel.isdisjoint(conflicts)
    assert ordered.isdisjoint(conflicts)


def test_compatible_events_remain_parallel_when_other_events_conflict():
    initial = State(
        balances={
            "alice": 10,
            "bob": 0,
            "carol": 5,
            "dave": 0,
        }
    )

    compatible_a = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    compatible_b = Transfer(
        "carol",
        "dave",
        2,
        0,
    )

    conflict_a = Transfer(
        "alice",
        "bob",
        10,
        1,
    )

    conflict_b = Transfer(
        "alice",
        "dave",
        9,
        1,
    )

    plan = build_state_execution_plan(
        initial,
        [
            compatible_a,
            compatible_b,
            conflict_a,
            conflict_b,
        ],
    )

    compatible_pair = (
        compatible_a.event_id(),
        compatible_b.event_id(),
    )

    conflict_pair = (
        conflict_a.event_id(),
        conflict_b.event_id(),
    )

    assert compatible_pair in plan.parallel
    assert conflict_pair in plan.conflicts
    assert plan.has_conflicts()
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

    plan = build_state_execution_plan(initial, events)

    assert len(plan.parallel) == 6
    assert not plan.ordered
    assert not plan.conflicts
