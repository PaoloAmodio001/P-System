import pytest

from core.conflict_state import ConflictState
from core.event import Transfer
from core.state import State
from network.conflicted_state import ConflictedState


def test_conflicted_state_blocks_execution():
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

    conflicted = ConflictedState(
        base_state=State({"alice": 10}),
        alternatives=ConflictState(
            (tx_a, tx_b)
        ),
    )

    assert conflicted.is_conflicted
    assert not conflicted.has_winner

    # A conflicted state must not select
    # or execute either alternative.
    assert conflicted.contains(tx_a)
    assert conflicted.contains(tx_b)

    with pytest.raises(ValueError):
        if conflicted.is_conflicted:
            raise ValueError(
                "CANNOT EXECUTE CONFLICTED STATE"
            )
