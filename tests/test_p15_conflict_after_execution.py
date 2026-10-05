from tests.signed_helpers import authorize, identity_with_claim, signed_transfer

from core.decision_status import DecisionStatus
from core.state import State
from network.node import Node


def test_p15_conflict_discovered_after_execution_preserves_local_projection():
    node = Node("p15-after-execution", State({"alice": 8}), port=0)

    try:
        identity, claim = identity_with_claim("alice")
        authorize(node, claim)

        tx_a, signed_a = signed_transfer(identity, "alice", "bob", 8, 0)
        tx_b, signed_b = signed_transfer(identity, "alice", "carol", 8, 0)

        assert node.receive_signed(signed_a, broadcast=False)
        assert tx_a in node.local_events
        assert node.state.balance("bob") == 8

        assert node.receive_signed(signed_b, broadcast=False) is False

        assert tx_a in node.events
        assert tx_b in node.events
        assert tx_a in node.local_events
        assert tx_b not in node.local_events

        assert node.status() == DecisionStatus.CONFLICTED
        assert node.state.balance("bob") == 8
        assert node.state.balance("carol") == 0
    finally:
        node.stop()
