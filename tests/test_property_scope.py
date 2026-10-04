from dataclasses import dataclass

from core.event import Transfer
from core.state import State
from core.proof import apply_transfer


@dataclass(frozen=True)
class PropertyScope:
    balances: frozenset[str]
    nonces: frozenset[str]

    def contains_balance(self, identity: str) -> bool:
        return identity in self.balances

    def contains_nonce(self, identity: str) -> bool:
        return identity in self.nonces


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


def test_balance_scope_can_be_smaller_than_identity_scope():
    scope = PropertyScope(
        balances=frozenset({"alice"}),
        nonces=frozenset(),
    )

    assert scope.contains_balance("alice")
    assert not scope.contains_balance("bob")
    assert not scope.contains_nonce("alice")


def test_independent_event_outside_property_scope_is_invisible():
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

    state_visible = apply_transfer(
        initial,
        visible,
    )

    state_extended = apply_transfer(
        state_visible,
        hidden,
    )

    scope = PropertyScope(
        balances=frozenset({"alice", "bob"}),
        nonces=frozenset(),
    )

    assert project_state(
        state_visible,
        scope,
    ) == project_state(
        state_extended,
        scope,
    )


def test_nonce_scope_detects_nonce_change():
    initial = State(
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
        initial,
        event,
    )

    scope = PropertyScope(
        balances=frozenset(),
        nonces=frozenset({"alice"}),
    )

    assert project_state(
        initial,
        scope,
    ) != project_state(
        updated,
        scope,
    )


def test_balance_only_scope_can_ignore_nonce_change():
    initial = State(
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
        initial,
        event,
    )

    scope = PropertyScope(
        balances=frozenset({"alice"}),
        nonces=frozenset(),
    )

    assert project_state(
        initial,
        scope,
    ) != project_state(
        updated,
        scope,
    )
