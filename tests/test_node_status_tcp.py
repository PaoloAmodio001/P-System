import time

from core.decision_status import DecisionStatus
from core.event import Transfer
from core.state import State
from network.node import Node


def test_nodes_become_conflicted_after_tcp_sync():
    node_a = Node(
        "node-A",
        State({"alice": 10}),
        port=0,
    )

    node_b = Node(
        "node-B",
        State({"alice": 10}),
        port=0,
    )

    node_a.start()
    node_b.start()

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

        assert node_a.receive(tx_a)
        assert node_b.receive(tx_b)

        assert node_a.status() == DecisionStatus.UNIQUE
        assert node_b.status() == DecisionStatus.UNIQUE

        node_a.sync_with(node_b)
        node_b.sync_with(node_a)

        deadline = time.time() + 2

        while (
            (
                len(node_a.events) < 2
                or len(node_b.events) < 2
            )
            and time.time() < deadline
        ):
            time.sleep(0.01)

        assert set(node_a.events) == {tx_a, tx_b}
        assert set(node_b.events) == {tx_a, tx_b}

        assert node_a.status() == DecisionStatus.CONFLICTED
        assert node_b.status() == DecisionStatus.CONFLICTED

    finally:
        node_a.stop()
        node_b.stop()
