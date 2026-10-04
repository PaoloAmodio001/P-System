from core.event import Transfer
from core.state import State
from core.proof import apply_transfer


def test_unrelated_hidden_event_does_not_change_state():
    initial = State(
        balances={
            "alice": 10,
            "carol": 10,
        },
        nonces={
            "alice": 0,
            "carol": 0,
        },
    )

    visible = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    hidden_unrelated = Transfer(
        "carol",
        "dave",
        2,
        0,
    )

    state_visible = apply_transfer(
        initial,
        visible,
    )

    state_with_hidden = apply_transfer(
        state_visible,
        hidden_unrelated,
    )

    assert state_visible.balance("alice") == 7
    assert state_visible.balance("bob") == 3

    assert state_with_hidden.balance("alice") == 7
    assert state_with_hidden.balance("bob") == 3

    assert state_with_hidden.balance("carol") == 8
    assert state_with_hidden.balance("dave") == 2


def test_hidden_event_can_change_relevant_state():
    initial = State(
        balances={
            "alice": 10,
        },
        nonces={
            "alice": 0,
        },
    )

    first = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    hidden_relevant = Transfer(
        "alice",
        "carol",
        4,
        1,
    )

    state_first = apply_transfer(
        initial,
        first,
    )

    state_with_hidden = apply_transfer(
        state_first,
        hidden_relevant,
    )

    assert state_first.balance("alice") == 7
    assert state_with_hidden.balance("alice") == 3

    assert state_first.root() != state_with_hidden.root()


def test_relevance_depends_on_state_domain():
    initial = State(
        balances={
            "alice": 10,
            "carol": 10,
        },
        nonces={
            "alice": 0,
            "carol": 0,
        },
    )

    visible = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    unrelated = Transfer(
        "carol",
        "dave",
        2,
        0,
    )

    relevant = Transfer(
        "alice",
        "erin",
        2,
        1,
    )

    state = apply_transfer(
        initial,
        visible,
    )

    unrelated_state = apply_transfer(
        state,
        unrelated,
    )

    relevant_state = apply_transfer(
        state,
        relevant,
    )

    assert unrelated_state.balance("alice") == 7
    assert relevant_state.balance("alice") == 5

    assert unrelated_state.root() != relevant_state.root()
