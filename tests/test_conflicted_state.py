from core.conflict_state import ConflictState
from core.event import Transfer
from core.state import State
from network.conflicted_state import ConflictedState


def test_conflicted_state_has_no_winner():
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

    state = ConflictedState(
        base_state=State({"alice": 10}),
        alternatives=ConflictState(
            (tx_a, tx_b)
        ),
    )

    assert state.is_conflicted
    assert not state.has_winner

    assert state.contains(tx_a)
    assert state.contains(tx_b)
