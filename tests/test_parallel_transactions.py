from core.state import State
from core.event import Transfer
from core.derive import StateDeriver


def test_parallel_independent_transactions():
    initial = State({
        "alice": 10,
        "bob": 10,
        "carol": 0,
        "dave": 0,
    })

    tx_a = Transfer(
        sender="alice",
        receiver="carol",
        amount=4,
        nonce=0,
    )

    tx_b = Transfer(
        sender="bob",
        receiver="dave",
        amount=6,
        nonce=0,
    )

    state_ab = StateDeriver.apply_events(
        initial,
        [tx_a, tx_b],
    )

    state_ba = StateDeriver.apply_events(
        initial,
        [tx_b, tx_a],
    )

    assert state_ab.root() == state_ba.root()

    assert state_ab.balance("alice") == 6
    assert state_ab.balance("bob") == 4
    assert state_ab.balance("carol") == 4
    assert state_ab.balance("dave") == 6

    assert state_ab.nonce("alice") == 1
    assert state_ab.nonce("bob") == 1
