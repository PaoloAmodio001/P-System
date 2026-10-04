from core.state import State
from core.event import Transfer
from core.conflict import Conflict


def test_detect_double_spend_conflict():
    initial = State({
        "alice": 10,
        "bob": 0,
        "carol": 0,
    })

    tx_a = Transfer(
        "alice",
        "bob",
        8,
        0,
    )

    tx_b = Transfer(
        "alice",
        "carol",
        8,
        0,
    )

    state_a = initial.copy()
    state_b = initial.copy()

    state_a.balances["alice"] -= 8
    state_a.balances["bob"] = 8
    state_a.nonces["alice"] = 1

    state_b.balances["alice"] -= 8
    state_b.balances["carol"] = 8
    state_b.nonces["alice"] = 1

    conflict = Conflict(
        state_a=state_a,
        tx_a=tx_a,
        state_b=state_b,
        tx_b=tx_b,
    )

    assert conflict.is_double_spend()

    root_a, root_b = conflict.roots()

    assert root_a != root_b

    description = conflict.describe()

    assert description["type"] == "DOUBLE_SPEND"
    assert description["sender"] == "alice"
    assert description["nonce"] == 0
