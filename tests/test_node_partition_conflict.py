import time

from core.event import Transfer
from core.state import State
from network.node import Node


def test_node_partition_conflict_without_winner():
    node_a = Node(
        node_id="node-A",
        initial_state=State({"alice": 10}),
        port=0,
    )

    node_b = Node(
        node_id="node-B",
        initial_state=State({"alice": 10}),
        port=0,
    )

    node_a.start()
    node_b.start()

    try:
        tx_a = Transfer(
            sender="alice",
            receiver="bob",
            amount=8,
            nonce=0,
        )

        tx_b = Transfer(
            sender="alice",
            receiver="carol",
            amount=8,
            nonce=0,
        )

        # Partition:
        # A accepts tx_a locally.
        # B accepts tx_b locally.
        assert node_a.receive(tx_a)
        assert node_b.receive(tx_b)

        root_a = node_a.state_root()
        root_b = node_b.state_root()

        assert root_a != root_b

        # Both states are locally valid.
        assert node_a.state.balance("alice") == 2
        assert node_a.state.balance("bob") == 8

        assert node_b.state.balance("alice") == 2
        assert node_b.state.balance("carol") == 8

        # The two alternatives are preserved locally.
        assert tx_a in node_a.events
        assert tx_b in node_b.events

        # No automatic winner exists.
        assert tx_a != tx_b

    finally:
        node_a.stop()
        node_b.stop()
