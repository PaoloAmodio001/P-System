from core.commutativity import commute
from core.event import Transfer
from core.state import State


def test_independent_transfers_commute():
    initial = State({
        "alice": 10,
        "bob": 10,
        "carol": 0,
        "dave": 0,
    })

    first = Transfer(
        sender="alice",
        receiver="carol",
        amount=5,
        nonce=0,
    )

    second = Transfer(
        sender="bob",
        receiver="dave",
        amount=5,
        nonce=0,
    )

    assert commute(initial, first, second)


def test_conflicting_transfers_do_not_commute():
    initial = State({
        "alice": 10,
        "bob": 0,
        "carol": 0,
    })

    first = Transfer(
        sender="alice",
        receiver="bob",
        amount=8,
        nonce=0,
    )

    second = Transfer(
        sender="alice",
        receiver="carol",
        amount=8,
        nonce=0,
    )

    assert not commute(initial, first, second)


def test_same_sender_different_nonces_can_commute_when_valid():
    initial = State({
        "alice": 10,
        "bob": 0,
        "carol": 0,
    })

    first = Transfer(
        sender="alice",
        receiver="bob",
        amount=4,
        nonce=0,
    )

    second = Transfer(
        sender="alice",
        receiver="carol",
        amount=3,
        nonce=1,
    )

    assert not commute(initial, first, second)


def test_invalid_operation_does_not_commute():
    initial = State({
        "alice": 5,
        "bob": 0,
        "carol": 0,
    })

    first = Transfer(
        sender="alice",
        receiver="bob",
        amount=10,
        nonce=0,
    )

    second = Transfer(
        sender="carol",
        receiver="bob",
        amount=1,
        nonce=0,
    )

    assert not commute(initial, first, second)
