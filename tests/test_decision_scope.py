from dataclasses import dataclass

from core.event import Transfer
from core.state import State
from core.proof import apply_transfer


@dataclass(frozen=True)
class DecisionScope:
    identities: frozenset[str]

    def contains(self, identity: str) -> bool:
        return identity in self.identities


def project_state(
    state: State,
    scope: DecisionScope,
) -> tuple:
    balances = tuple(
        sorted(
            (identity, state.balance(identity))
            for identity in scope.identities
        )
    )

    nonces = tuple(
        sorted(
            (identity, state.nonce(identity))
            for identity in scope.identities
        )
    )

    return balances, nonces


def test_scope_contains_only_decision_relevant_identities():
    scope = DecisionScope(
        identities=frozenset({"alice", "bob"})
    )

    assert scope.contains("alice")
    assert scope.contains("bob")
    assert not scope.contains("carol")


def test_independent_extension_preserves_scoped_decision():
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

    scope = DecisionScope(
        identities=frozenset({"alice", "bob"})
    )

    state_visible = apply_transfer(
        initial,
        visible,
    )

    state_extended = apply_transfer(
        state_visible,
        hidden,
    )

    assert project_state(
        state_visible,
        scope,
    ) == project_state(
        state_extended,
        scope,
    )


def test_extension_inside_scope_changes_decision():
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
        sender="alice",
        receiver="carol",
        amount=2,
        nonce=1,
    )

    scope = DecisionScope(
        identities=frozenset({"alice", "bob"})
    )

    state_visible = apply_transfer(
        initial,
        visible,
    )

    state_extended = apply_transfer(
        state_visible,
        hidden,
    )

    assert project_state(
        state_visible,
        scope,
    ) != project_state(
        state_extended,
        scope,
    )


def test_scope_must_include_sender_to_capture_balance_change():
    initial = State(
        balances={
            "alice": 10,
            "bob": 0,
        },
        nonces={
            "alice": 0,
            "bob": 0,
        },
    )

    event = Transfer(
        sender="alice",
        receiver="bob",
        amount=3,
        nonce=0,
    )

    state = apply_transfer(
        initial,
        event,
    )

    scope = DecisionScope(
        identities=frozenset({"alice"})
    )

    assert project_state(
        initial,
        scope,
    ) != project_state(
        state,
        scope,
    )
