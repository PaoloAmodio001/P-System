from core.state import State
from core.event import Transfer
from core.proof import verify_transfer, apply_transfer


def test_valid_transfer():
    state = State({"alice": 10})

    tx = Transfer(
        sender="alice",
        receiver="bob",
        amount=3,
        nonce=0,
    )

    assert verify_transfer(state, tx)

    new_state = apply_transfer(state, tx)

    assert new_state.balance("alice") == 7
    assert new_state.balance("bob") == 3


def test_double_spending_same_state():
    state = State({"alice": 10})

    tx1 = Transfer("alice", "bob", 8, 0)
    tx2 = Transfer("alice", "carol", 8, 0)

    assert verify_transfer(state, tx1)
    assert verify_transfer(state, tx2)

    state = apply_transfer(state, tx1)

    assert not verify_transfer(state, tx2)


def test_insufficient_balance():
    state = State({"alice": 10})

    tx = Transfer("alice", "bob", 11, 0)

    assert not verify_transfer(state, tx)
