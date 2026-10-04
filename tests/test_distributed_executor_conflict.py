import pytest

from core.conflict_state import ConflictState
from core.distributed_executor import DistributedExecutor
from core.event import Transfer
from core.state import State
from network.conflicted_state import ConflictedState


def test_distributed_executor_rejects_conflicted_state():
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

    executor = DistributedExecutor("node-A")

    with pytest.raises(ValueError, match="CONFLICTING PLAN"):
        executor.execute(
            conflicted.base_state,
            [tx_a, tx_b],
            executor.plan_state(
                conflicted.base_state,
                [tx_a, tx_b],
            ),
        )
