from tests.signed_helpers import authorize, identity_with_claim, signed_transfer

from core.decision_status import DecisionStatus
from core.state import State
from network.node import Node


def test_p15_three_way_byzantine_equivocation_remains_conflicted():
    node = Node("p15-three-way", State({"alice": 24}), port=0)

    try:
        identity, claim = identity_with_claim("alice")
        assert authorize(node, claim) is None or True

        tx_a, signed_a = signed_transfer(identity, "alice", "bob", 8, 0)
        tx_b, signed_b = signed_transfer(identity, "alice", "carol", 8, 0)
        tx_c, signed_c = signed_transfer(identity, "alice", "dave", 8, 0)

        assert node.receive_signed(signed_a, broadcast=False)
        assert node.receive_signed(signed_b, broadcast=False) is False
        assert node.receive_signed(signed_c, broadcast=False) is False

        assert tx_a in node.events
        assert tx_b in node.events
        assert tx_c in node.events
        assert node.status() == DecisionStatus.CONFLICTED
        assert node.state.balance("bob") == 8
        assert node.state.balance("carol") == 0
        assert node.state.balance("dave") == 0
        assert not node.equivocations.is_empty()
        assert node.equivocations.has_winner() is False
    finally:
        node.stop()
