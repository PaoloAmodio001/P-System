from core.event import Transfer
from core.state import State


def apply_pair(initial, first, second):
    from core.proof import apply_transfer

    try:
        apply_transfer(
            apply_transfer(initial, first),
            second,
        )
        first_valid = True
    except ValueError:
        first_valid = False

    try:
        apply_transfer(
            apply_transfer(initial, second),
            first,
        )
        second_valid = True
    except ValueError:
        second_valid = False

    return first_valid, second_valid


def test_compatible_events():
    initial = State(
        balances={
            "alice": 10,
            "bob": 0,
            "carol": 10,
            "dave": 0,
        }
    )

    first = Transfer("alice", "bob", 3, 0)
    second = Transfer("carol", "dave", 2, 0)

    first_valid, second_valid = apply_pair(
        initial,
        first,
        second,
    )

    assert first_valid
    assert second_valid


def test_order_dependent_events():
    initial = State(
        balances={
            "alice": 5,
            "bob": 0,
            "carol": 0,
        }
    )

    first = Transfer("alice", "bob", 5, 0)
    second = Transfer("bob", "carol", 5, 0)

    first_valid, second_valid = apply_pair(
        initial,
        first,
        second,
    )

    assert first_valid
    assert not second_valid


def test_absolute_conflict():
    initial = State(
        balances={
            "alice": 5,
            "bob": 0,
            "carol": 0,
        }
    )

    first = Transfer("alice", "bob", 5, 0)
    second = Transfer("alice", "carol", 4, 1)

    first_valid, second_valid = apply_pair(
        initial,
        first,
        second,
    )

    assert not first_valid
    assert not second_valid
