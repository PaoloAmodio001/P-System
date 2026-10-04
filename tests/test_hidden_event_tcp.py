from core.decision_status import DecisionStatus
from core.event import Transfer
from core.state import State
from network.node import Node
import time


def test_hidden_conflict_changes_status_via_tcp():
    node_a = Node("node-A", State({"alice": 10}))
    node_b = Node("node-B", State({"alice": 10}))

    tx_a = Transfer("alice", "bob", 8, 0)
    tx_b = Transfer("alice", "carol", 8, 0)

    try:
        node_a.start()
        node_b.start()

        assert node_a.receive(tx_a)
        assert node_a.status() == DecisionStatus.UNIQUE

        assert node_b.receive(tx_b)
        assert node_b.status() == DecisionStatus.UNIQUE

        # tx_b is unknown to node A.
        # Node B sends it to Node A through the real TCP transport.
        node_b.sync_with(node_a)

        # Give the server thread time to process the message.
        time.sleep(0.1)

        assert tx_b in node_a.events
        assert node_a.status() == DecisionStatus.CONFLICTED

        # The already-applied local state is preserved.
        assert node_a.state.balance("alice") == 2
        assert node_a.state.balance("bob") == 8
        assert node_a.state.balance("carol") == 0

    finally:
        node_a.stop()
        node_b.stop()
