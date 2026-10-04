from core.decision_status import DecisionStatus
from core.event import Transfer
from core.state import State
from network.node import Node
import time


def test_adversarial_node_cannot_make_peers_forget_conflicting_events():
    honest_a = Node("honest-A", State({"alice": 10}))
    honest_b = Node("honest-B", State({"alice": 10}))
    adversary = Node("adversary", State({"alice": 10}))

    tx_a = Transfer("alice", "bob", 8, 0)
    tx_b = Transfer("alice", "carol", 8, 0)

    try:
        honest_a.start()
        honest_b.start()
        adversary.start()

        # Honest nodes independently observe incompatible alternatives.
        assert honest_a.receive(tx_a)
        assert honest_b.receive(tx_b)

        assert honest_a.status() == DecisionStatus.UNIQUE
        assert honest_b.status() == DecisionStatus.UNIQUE

        # Adversary learns both alternatives.
        adversary.events.extend([tx_a, tx_b])

        # Adversary disseminates inconsistent subsets.
        adversary.events = [tx_a]
        adversary.sync_with(honest_b)

        adversary.events = [tx_b]
        adversary.sync_with(honest_a)

        time.sleep(0.1)

        # Honest nodes must retain their original local states.
        assert honest_a.state.balance("bob") == 8
        assert honest_a.state.balance("carol") == 0

        assert honest_b.state.balance("bob") == 0
        assert honest_b.state.balance("carol") == 8

        # Once the honest nodes exchange knowledge directly,
        # the conflict becomes explicit on both sides.
        honest_a.sync_with(honest_b)
        honest_b.sync_with(honest_a)

        time.sleep(0.1)

        assert tx_a in honest_a.events
        assert tx_b in honest_a.events
        assert tx_a in honest_b.events
        assert tx_b in honest_b.events

        assert honest_a.status() == DecisionStatus.CONFLICTED
        assert honest_b.status() == DecisionStatus.CONFLICTED

        # No alternative becomes the winner.
        assert honest_a.state.balance("bob") == 8
        assert honest_a.state.balance("carol") == 0

        assert honest_b.state.balance("bob") == 0
        assert honest_b.state.balance("carol") == 8

    finally:
        honest_a.stop()
        honest_b.stop()
        adversary.stop()
