import pytest

from core.conflict_state import ConflictState
from core.distributed_executor import DistributedExecutor
from core.event import Transfer
from core.state import State
from network.conflicted_state import ConflictedState
from network.node import Node
from network.reconciliation import reconcile


def test_reconciled_nodes_block_conflicting_execution():
    initial = State({"alice": 10})

    node_a = Node(
        "node-A",
        initial,
    )

    node_b = Node(
        "node-B",
        initial,
    )

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

    assert node_a.receive(tx_a)
    assert node_b.receive(tx_b)

    reconcile(node_a, node_b)

    conflict = ConflictState(
        tuple(sorted(
            [tx_a, tx_b],
            key=lambda event: event.event_id(),
        ))
    )

    conflicted = ConflictedState(
        base_state=initial,
        alternatives=conflict,
    )

    assert conflicted.is_conflicted
    assert not conflicted.has_winner

    executor = DistributedExecutor(
        node_a.node_id
    )

    plan = executor.plan_state(
        initial,
        [tx_a, tx_b],
    )

    with pytest.raises(
        ValueError,
        match="CONFLICTING PLAN",
    ):
        executor.execute(
            initial,
            [tx_a, tx_b],
            plan,
        )
