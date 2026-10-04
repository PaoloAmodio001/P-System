from core.state import State
from core.event import Transfer
from core.verifiable_state import VerifiableState


def test_verifiable_state_is_created():
    initial = State(
        balances={"alice": 10},
        nonces={"alice": 0},
    )

    event = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    result = VerifiableState.create(
        initial,
        [event],
    )

    assert result.state_root

    assert result.verify(
        initial,
        [event],
    ) is True


def test_verifiable_state_detects_tampered_event():
    initial = State(
        balances={"alice": 10},
        nonces={"alice": 0},
    )

    event = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    result = VerifiableState.create(
        initial,
        [event],
    )

    tampered = Transfer(
        "alice",
        "carol",
        3,
        0,
    )

    assert result.verify(
        initial,
        [tampered],
    ) is False


def test_verifiable_state_detects_wrong_initial_state():
    initial = State(
        balances={"alice": 10},
        nonces={"alice": 0},
    )

    event = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    result = VerifiableState.create(
        initial,
        [event],
    )

    different_initial = State(
        balances={"alice": 20},
        nonces={"alice": 0},
    )

    assert result.verify(
        different_initial,
        [event],
    ) is False


def test_verifiable_state_rejects_invalid_transfer():
    initial = State(
        balances={"alice": 2},
        nonces={"alice": 0},
    )

    event = Transfer(
        "alice",
        "bob",
        5,
        0,
    )

    try:
        VerifiableState.create(
            initial,
            [event],
        )
        assert False
    except ValueError:
        assert True


def test_verifiable_state_rejects_conflicting_events():
    initial = State(
        balances={"alice": 10},
        nonces={"alice": 0},
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
        4,
        0,
    )

    try:
        VerifiableState.create(
            initial,
            [first, second],
        )
        assert False
    except ValueError:
        assert True
