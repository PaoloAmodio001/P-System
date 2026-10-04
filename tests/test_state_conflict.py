from core.event import Transfer
from core.state import State
from core.state_conflict import state_conflict


def test_balance_conflict():
    initial = State(
        balances={
            "alice": 5,
            "bob": 0,
            "carol": 0,
        }
    )

    first = Transfer(
        "alice",
        "bob",
        5,
        0,
    )

    second = Transfer(
        "alice",
        "carol",
        4,
        1,
    )

    assert state_conflict(
        initial,
        first,
        second,
    )


def test_independent_events_do_not_conflict():
    initial = State(
        balances={
            "alice": 5,
            "bob": 0,
            "carol": 5,
            "dave": 0,
        }
    )

    first = Transfer(
        "alice",
        "bob",
        5,
        0,
    )

    second = Transfer(
        "carol",
        "dave",
        5,
        0,
    )

    assert not state_conflict(
        initial,
        first,
        second,
    )


def test_compatible_events_do_not_conflict():
    initial = State(
        balances={
            "alice": 10,
            "bob": 0,
            "carol": 0,
        }
    )

    first = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    second = Transfer(
        "alice",
        "carol",
        2,
        1,
    )

    assert not state_conflict(
        initial,
        first,
        second,
    )
