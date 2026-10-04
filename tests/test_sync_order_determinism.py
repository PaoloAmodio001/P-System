from core.decision_status import DecisionStatus
from core.event import Transfer
from core.state import State
from network.node import Node
import time


def test_conflict_status_is_independent_of_sync_order_and_duplicates():
    node_a = Node("node-A", State({"alice": 10}))
    node_b = Node("node-B", State({"alice": 10}))

    tx_a = Transfer("alice", "bob", 8, 0)
    tx_b = Transfer("alice", "carol", 8, 0)

    try:
        node_a.start()
        node_b.start()

        assert node_a.receive(tx_a)
        assert node_b.receive(tx_b)

        # Exchange in opposite directions.
        node_a.sync_with(node_b)
        time.sleep(0.05)
        node_b.sync_with(node_a)

        # Repeat the same synchronization.
        node_a.sync_with(node_b)
        node_b.sync_with(node_a)

        time.sleep(0.1)

        assert node_a.status() == DecisionStatus.CONFLICTED
        assert node_b.status() == DecisionStatus.CONFLICTED

        # Both alternatives remain known.
        assert tx_a in node_a.events
        assert tx_b in node_a.events
        assert tx_a in node_b.events
        assert tx_b in node_b.events

        # Duplicate synchronization must not alter local state.
        assert node_a.state.balance("alice") == 2
        assert node_a.state.balance("bob") == 8
        assert node_a.state.balance("carol") == 0

        assert node_b.state.balance("alice") == 2
        assert node_b.state.balance("bob") == 0
        assert node_b.state.balance("carol") == 8

    finally:
        node_a.stop()
        node_b.stop()
