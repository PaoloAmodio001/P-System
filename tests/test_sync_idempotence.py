import time

from core.decision_status import DecisionStatus
from core.event import Transfer
from core.state import State
from network.node import Node


def test_repeated_sync_is_idempotent():
    nodes = [
        Node(
            f"node-{i}",
            State({"alice": 10}),
            port=0,
        )
        for i in range(3)
    ]

    for node in nodes:
        node.start()

    try:
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

        assert nodes[0].receive(tx_a)
        assert nodes[1].receive(tx_b)

        nodes[0].sync_with(nodes[2])
        nodes[1].sync_with(nodes[2])

        deadline = time.time() + 2

        while (
            len(nodes[2].events) < 2
            and time.time() < deadline
        ):
            time.sleep(0.01)

        assert set(nodes[2].events) == {
            tx_a,
            tx_b,
        }

        # Repeat the same synchronization several times.
        for _ in range(5):
            nodes[0].sync_with(nodes[2])
            nodes[1].sync_with(nodes[2])
            nodes[2].sync_with(nodes[0])
            nodes[2].sync_with(nodes[1])

        time.sleep(0.1)

        # No duplicate knowledge.
        assert len(nodes[0].events) == 2
        assert len(nodes[1].events) == 2
        assert len(nodes[2].events) == 2

        assert set(nodes[0].events) == {tx_a, tx_b}
        assert set(nodes[1].events) == {tx_a, tx_b}
        assert set(nodes[2].events) == {tx_a, tx_b}

        # The conflict remains a conflict.
        assert nodes[0].status() == DecisionStatus.CONFLICTED
        assert nodes[1].status() == DecisionStatus.CONFLICTED
        assert nodes[2].status() == DecisionStatus.CONFLICTED

    finally:
        for node in nodes:
            node.stop()
