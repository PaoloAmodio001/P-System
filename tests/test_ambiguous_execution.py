from core.ambiguous_execution import ExecutionStatus, can_execute
from core.conflict_state import ConflictState
from core.event import Transfer
from core.state import State
from core.state_view import StateView


def test_unique_state_is_executable():
    view = StateView.unique(
        State(
            balances={
                "alice": 10,
                "bob": 0,
            }
        )
    )

    event = Transfer(
        "alice",
        "bob",
        2,
        0,
    )

    assert can_execute(view, event) == ExecutionStatus.EXECUTABLE


def test_independent_event_during_conflict_is_executable():
    event_a = Transfer(
        "alice",
        "bob",
        6,
        0,
    )

    event_b = Transfer(
        "alice",
        "carol",
        7,
        0,
    )

    conflict = ConflictState(
        alternatives=(event_a, event_b)
    )

    view = StateView.ambiguous(conflict)

    independent = Transfer(
        "dave",
        "erin",
        2,
        0,
    )

    events = [
        event_a,
        event_b,
        independent,
    ]

    assert can_execute(
        view,
        independent,
        events,
    ) == ExecutionStatus.EXECUTABLE


def test_direct_dependency_is_blocked():
    event_a = Transfer(
        "alice",
        "bob",
        6,
        0,
    )

    event_b = Transfer(
        "alice",
        "carol",
        7,
        0,
    )

    conflict = ConflictState(
        alternatives=(event_a, event_b)
    )

    view = StateView.ambiguous(conflict)

    dependent = Transfer(
        "bob",
        "dave",
        2,
        0,
        parents=(event_a.event_id(),),
    )

    events = [
        event_a,
        event_b,
        dependent,
    ]

    assert can_execute(
        view,
        dependent,
        events,
    ) == ExecutionStatus.BLOCKED


def test_transitive_dependency_is_blocked():
    event_a = Transfer(
        "alice",
        "bob",
        6,
        0,
    )

    event_b = Transfer(
        "alice",
        "carol",
        7,
        0,
    )

    intermediate = Transfer(
        "bob",
        "dave",
        2,
        0,
        parents=(event_a.event_id(),),
    )

    dependent = Transfer(
        "dave",
        "erin",
        1,
        0,
        parents=(intermediate.event_id(),),
    )

    conflict = ConflictState(
        alternatives=(event_a, event_b)
    )

    view = StateView.ambiguous(conflict)

    events = [
        event_a,
        event_b,
        intermediate,
        dependent,
    ]

    assert can_execute(
        view,
        dependent,
        events,
    ) == ExecutionStatus.BLOCKED


def test_missing_known_events_blocks_ambiguous_execution():
    event_a = Transfer(
        "alice",
        "bob",
        6,
        0,
    )

    event_b = Transfer(
        "alice",
        "carol",
        7,
        0,
    )

    conflict = ConflictState(
        alternatives=(event_a, event_b)
    )

    view = StateView.ambiguous(conflict)

    independent = Transfer(
        "dave",
        "erin",
        2,
        0,
    )

    assert can_execute(
        view,
        independent,
    ) == ExecutionStatus.BLOCKED
