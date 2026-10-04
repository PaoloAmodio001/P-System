from dataclasses import dataclass

from core.event import Transfer
from core.state import State
from core.proof import apply_transfer


@dataclass(frozen=True)
class PropertyScope:
    balances: frozenset[str]
    nonces: frozenset[str]


def project_state(
    state: State,
    scope: PropertyScope,
) -> tuple:
    balances = tuple(
        sorted(
            (identity, state.balance(identity))
            for identity in scope.balances
        )
    )

    nonces = tuple(
        sorted(
            (identity, state.nonce(identity))
            for identity in scope.nonces
        )
    )

    return balances, nonces


def test_nonce_controls_future_validity():
    state = State(
        balances={"alice": 10},
        nonces={"alice": 0},
    )

    first = Transfer(
        sender="alice",
        receiver="bob",
        amount=3,
        nonce=0,
    )

    future = Transfer(
        sender="alice",
        receiver="carol",
        amount=2,
        nonce=1,
    )

    updated = apply_transfer(
        state,
        first,
    )

    assert state.nonce("alice") == 0
    assert updated.nonce("alice") == 1

    # La seconda transazione diventa valida solo
    # dopo il cambiamento del nonce.
    assert future.nonce == updated.nonce("alice")


def test_balance_projection_alone_is_not_enough_for_future_validity():
    state = State(
        balances={"alice": 10},
        nonces={"alice": 0},
    )

    first = Transfer(
        sender="alice",
        receiver="bob",
        amount=3,
        nonce=0,
    )

    future = Transfer(
        sender="alice",
        receiver="carol",
        amount=2,
        nonce=1,
    )

    updated = apply_transfer(
        state,
        first,
    )

    balance_scope = PropertyScope(
        balances=frozenset({"alice"}),
        nonces=frozenset(),
    )

    # La proiezione del balance cambia.
    assert project_state(
        state,
        balance_scope,
    ) != project_state(
        updated,
        balance_scope,
    )

    # Ma il nonce, che non appartiene allo scope,
    # determina la validità della futura transazione.
    assert future.nonce != state.nonce("alice")
    assert future.nonce == updated.nonce("alice")


def test_cross_property_dependency_must_be_tracked():
    state = State(
        balances={"alice": 10},
        nonces={"alice": 0},
    )

    event = Transfer(
        sender="alice",
        receiver="bob",
        amount=3,
        nonce=0,
    )

    updated = apply_transfer(
        state,
        event,
    )

    # Balance e nonce vengono modificati dallo stesso evento.
    assert state.balance("alice") != updated.balance("alice")
    assert state.nonce("alice") != updated.nonce("alice")

    # Non possiamo considerare il nonce completamente
    # irrilevante se la decisione riguarda future
    # transazioni di Alice.
    assert updated.nonce("alice") == 1
