from core.decision_status import DecisionStatus
from core.event import Transfer
from core.state import State
from network.node import Node
import time


def test_partition_reconnect_preserves_both_conflicting_alternatives():
    node_a = Node("node-A", State({"alice": 10}))
    node_b = Node("node-B", State({"alice": 10}))

    tx_a = Transfer("alice", "bob", 8, 0)
    tx_b = Transfer("alice", "carol", 8, 0)

    try:
        node_a.start()
        node_b.start()

        # Network partition: nodes operate independently.
        assert node_a.receive(tx_a)
        assert node_b.receive(tx_b)

        assert node_a.status() == DecisionStatus.UNIQUE
        assert node_b.status() == DecisionStatus.UNIQUE

        # Reconnection: exchange knowledge through TCP.
        node_a.sync_with(node_b)
        node_b.sync_with(node_a)

        time.sleep(0.1)

        # Both nodes now know both incompatible alternatives.
        assert tx_a in node_a.events
        assert tx_b in node_a.events
        assert tx_a in node_b.events
        assert tx_b in node_b.events

        assert node_a.status() == DecisionStatus.CONFLICTED
        assert node_b.status() == DecisionStatus.CONFLICTED

        # No winner: each node preserves its locally applied state.
        assert node_a.state.balance("bob") == 8
        assert node_a.state.balance("carol") == 0

        assert node_b.state.balance("bob") == 0
        assert node_b.state.balance("carol") == 8

        assert node_a.state.balance("alice") == 2
        assert node_b.state.balance("alice") == 2

    finally:
        node_a.stop()
        node_b.stop()
