from core.event import Transfer
from core.state import State


def relevant_domain(state: State, events: list[Transfer]) -> set[str]:
    domain = set()

    for event in events:
        domain.add(event.sender)
        domain.add(event.receiver)

    return domain


def test_event_inside_domain_can_still_be_irrelevant():
    state = State(
        balances={
            "alice": 10,
            "bob": 5,
        },
        nonces={
            "alice": 0,
            "bob": 0,
        },
    )

    visible = Transfer(
        sender="alice",
        receiver="bob",
        amount=3,
        nonce=0,
    )

    # Bob appartiene al dominio.
    # Tuttavia questo evento non è applicabile:
    # il nonce 1 non è ancora valido per Bob.
    hidden = Transfer(
        sender="bob",
        receiver="carol",
        amount=2,
        nonce=1,
    )

    domain = relevant_domain(
        state,
        [visible],
    )

    assert "bob" in domain

    # Ma l'evento nascosto non è una transizione valida
    # rispetto allo stato corrente.
    assert hidden.sender in domain
    assert hidden.nonce != state.nonce(hidden.sender)


def test_domain_is_only_an_overapproximation():
    state = State(
        balances={
            "alice": 10,
            "bob": 5,
        },
        nonces={
            "alice": 0,
            "bob": 0,
        },
    )

    visible = Transfer(
        sender="alice",
        receiver="bob",
        amount=3,
        nonce=0,
    )

    hidden = Transfer(
        sender="bob",
        receiver="carol",
        amount=2,
        nonce=99,
    )

    domain = relevant_domain(
        state,
        [visible],
    )

    assert hidden.sender in domain

    # Essere nel dominio non implica automaticamente
    # essere una transizione capace di modificare lo stato.
    assert hidden.nonce != state.nonce(hidden.sender)
