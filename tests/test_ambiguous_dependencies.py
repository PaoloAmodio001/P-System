from core.ambiguous_execution import ExecutionStatus, can_execute
from core.conflict_state import ConflictState
from core.event import Transfer
from core.state_view import StateView


def test_unrelated_event_is_executable():
    conflict_a = Transfer(
        "alice",
        "bob",
        6,
        0,
    )

    conflict_b = Transfer(
        "alice",
        "carol",
        7,
        0,
    )

    view = StateView.ambiguous(
        ConflictState(
            alternatives=(conflict_a, conflict_b)
        )
    )

    event = Transfer(
        "dave",
        "erin",
        2,
        0,
    )

    assert can_execute(
        view,
        event,
        [conflict_a, conflict_b, event],
    ) == ExecutionStatus.EXECUTABLE


def test_event_using_conflicted_output_is_blocked():
    conflict_a = Transfer(
        "alice",
        "bob",
        6,
        0,
    )

    conflict_b = Transfer(
        "alice",
        "carol",
        7,
        0,
    )

    view = StateView.ambiguous(
        ConflictState(
            alternatives=(conflict_a, conflict_b)
        )
    )

    event = Transfer(
        "bob",
        "dave",
        2,
        0,
    )

    assert can_execute(view, event) == ExecutionStatus.BLOCKED


def test_event_using_non_conflicted_identity_remains_executable():
    conflict_a = Transfer(
        "alice",
        "bob",
        6,
        0,
    )

    conflict_b = Transfer(
        "alice",
        "carol",
        7,
        0,
    )

    view = StateView.ambiguous(
        ConflictState(
            alternatives=(conflict_a, conflict_b)
        )
    )

    event = Transfer(
        "dave",
        "erin",
        2,
        0,
    )

    assert can_execute(
        view,
        event,
        [conflict_a, conflict_b, event],
    ) == ExecutionStatus.EXECUTABLE


def test_conflict_propagates_transitively():
    conflict_a = Transfer(
        "alice",
        "bob",
        6,
        0,
    )

    conflict_b = Transfer(
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
        parents=(conflict_a.event_id(),),
    )

    downstream = Transfer(
        "dave",
        "erin",
        1,
        0,
        parents=(intermediate.event_id(),),
    )

    independent = Transfer(
        "frank",
        "gina",
        2,
        0,
    )

    view = StateView.ambiguous(
        ConflictState(
            alternatives=(conflict_a, conflict_b)
        )
    )

    events = [
        conflict_a,
        conflict_b,
        intermediate,
        downstream,
        independent,
    ]

    assert can_execute(
        view,
        downstream,
        events,
    ) == ExecutionStatus.BLOCKED

    assert can_execute(
        view,
        independent,
        events,
    ) == ExecutionStatus.EXECUTABLE
