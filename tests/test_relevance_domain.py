from core.event import Transfer
from core.state import State


def relevant_domain(state: State, events: list[Transfer]) -> set[str]:
    domain = set()

    for event in events:
        domain.add(event.sender)
        domain.add(event.receiver)

    return domain


def test_relevance_domain_contains_accounts_touched_by_state():
    state = State(
        balances={
            "alice": 10,
            "carol": 10,
        },
        nonces={
            "alice": 0,
            "carol": 0,
        },
    )

    event = Transfer(
        sender="alice",
        receiver="bob",
        amount=3,
        nonce=0,
    )

    domain = relevant_domain(
        state,
        [event],
    )

    assert "alice" in domain
    assert "bob" in domain
    assert "carol" not in domain


def test_event_outside_domain_is_structurally_unrelated():
    state = State(
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
        sender="alice",
        receiver="bob",
        amount=3,
        nonce=0,
    )

    hidden = Transfer(
        sender="carol",
        receiver="dave",
        amount=2,
        nonce=0,
    )

    domain = relevant_domain(
        state,
        [visible],
    )

    assert hidden.sender not in domain
    assert hidden.receiver not in domain


def test_event_inside_domain_is_potentially_relevant():
    state = State(
        balances={
            "alice": 10,
        },
        nonces={
            "alice": 0,
        },
    )

    visible = Transfer(
        sender="alice",
        receiver="bob",
        amount=3,
        nonce=0,
    )

    hidden = Transfer(
        sender="alice",
        receiver="carol",
        amount=4,
        nonce=0,
    )

    domain = relevant_domain(
        state,
        [visible],
    )

    assert hidden.sender in domain
