from core.event import Transfer
from core.state import State
from core.proof import apply_transfer


def test_hidden_event_can_become_relevant_through_hidden_predecessor():
    state = State(
        balances={
            "alice": 10,
            "bob": 0,
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

    hidden_a = Transfer(
        sender="alice",
        receiver="bob",
        amount=4,
        nonce=0,
    )

    hidden_b = Transfer(
        sender="bob",
        receiver="carol",
        amount=2,
        nonce=0,
        parents=(hidden_a.event_id(),),
    )

    # hidden_b non è applicabile allo stato corrente:
    # Bob non possiede ancora i fondi necessari.
    assert state.balance("bob") == 0

    # Ma hidden_a può creare quei fondi.
    state_after_a = apply_transfer(
        state,
        hidden_a,
    )

    state_after_b = apply_transfer(
        state_after_a,
        hidden_b,
    )

    assert state_after_b.balance("bob") == 2
    assert state_after_b.balance("carol") == 2


def test_transitive_dependency_makes_hidden_chain_relevant():
    state = State(
        balances={
            "alice": 10,
            "bob": 0,
            "carol": 0,
        },
        nonces={
            "alice": 0,
            "bob": 0,
            "carol": 0,
        },
    )

    hidden_a = Transfer(
        sender="alice",
        receiver="bob",
        amount=5,
        nonce=0,
    )

    hidden_b = Transfer(
        sender="bob",
        receiver="carol",
        amount=3,
        nonce=0,
        parents=(hidden_a.event_id(),),
    )

    hidden_c = Transfer(
        sender="carol",
        receiver="dave",
        amount=2,
        nonce=0,
        parents=(hidden_b.event_id(),),
    )

    state_a = apply_transfer(state, hidden_a)
    state_b = apply_transfer(state_a, hidden_b)
    state_c = apply_transfer(state_b, hidden_c)

    assert state_c.balance("dave") == 2

    assert hidden_b.parents == (hidden_a.event_id(),)
    assert hidden_c.parents == (hidden_b.event_id(),)


def test_visible_conflict_does_not_remove_hidden_causal_relevance():
    state = State(
        balances={
            "alice": 10,
            "bob": 0,
            "carol": 0,
        },
        nonces={
            "alice": 0,
            "bob": 0,
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
        amount=5,
        nonce=0,
    )

    hidden_child = Transfer(
        sender="carol",
        receiver="dave",
        amount=2,
        nonce=0,
        parents=(hidden.event_id(),),
    )

    # Visible e hidden sono alternative incompatibili.
    assert visible.sender == hidden.sender
    assert visible.nonce == hidden.nonce
    assert visible.event_id() != hidden.event_id()

    # Il figlio dipende causalmente dall'alternativa nascosta.
    assert hidden_child.parents == (hidden.event_id(),)
