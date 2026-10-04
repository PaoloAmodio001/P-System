from core.event import Transfer
from core.local_validity import locally_valid
from core.state import State


def test_event_can_be_valid_in_one_state():
    state = State({
        "alice": 10,
        "bob": 0,
    })

    event = Transfer(
        sender="alice",
        receiver="bob",
        amount=8,
        nonce=0,
    )

    assert locally_valid(state, event)


def test_same_event_can_be_invalid_in_another_state():
    state = State({
        "alice": 5,
        "bob": 0,
    })

    event = Transfer(
        sender="alice",
        receiver="bob",
        amount=8,
        nonce=0,
    )

    assert not locally_valid(state, event)


def test_nonce_is_state_dependent():
    state = State(
        balances={
            "alice": 10,
            "bob": 0,
        },
        nonces={
            "alice": 1,
        },
    )

    event = Transfer(
        sender="alice",
        receiver="bob",
        amount=5,
        nonce=0,
    )

    assert not locally_valid(state, event)


def test_local_validity_does_not_choose_between_states():
    state_a = State({
        "alice": 10,
        "bob": 0,
        "carol": 0,
    })

    state_b = State({
        "alice": 10,
        "bob": 0,
        "carol": 0,
    })

    event_a = Transfer(
        sender="alice",
        receiver="bob",
        amount=8,
        nonce=0,
    )

    event_b = Transfer(
        sender="alice",
        receiver="carol",
        amount=8,
        nonce=0,
    )

    assert locally_valid(state_a, event_a)
    assert locally_valid(state_b, event_b)


def test_invalid_amount_is_rejected_locally():
    state = State({
        "alice": 10,
        "bob": 0,
    })

    event = Transfer(
        sender="alice",
        receiver="bob",
        amount=0,
        nonce=0,
    )

    assert not locally_valid(state, event)
