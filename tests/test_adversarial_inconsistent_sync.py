import time
from tests.signed_helpers import authorize, identity_with_claim, signed_transfer
from core.decision_status import DecisionStatus
from core.state import State
from network.node import Node

def test_adversarial_node_cannot_make_peers_forget_conflicting_events():
    honest_a=Node("honest-A",State({"alice":10})); honest_b=Node("honest-B",State({"alice":10})); adversary=Node("adversary",State({"alice":10}))
    try:
        honest_a.start(); honest_b.start(); adversary.start()
        identity,claim=identity_with_claim("alice")
        for node in (honest_a,honest_b,adversary): authorize(node,claim)
        tx_a,signed_a=signed_transfer(identity,"alice","bob",8,0); tx_b,signed_b=signed_transfer(identity,"alice","carol",8,0)
        assert honest_a.receive_signed(signed_a,broadcast=False); assert honest_b.receive_signed(signed_b,broadcast=False)
        assert honest_a.status()==DecisionStatus.UNIQUE and honest_b.status()==DecisionStatus.UNIQUE
        adversary.receive_signed(signed_a,broadcast=False); adversary.receive_signed(signed_b,broadcast=False)
        adversary.signed_events={signed_a.transfer.event_id():signed_a}; adversary.sync_with(honest_b)
        adversary.signed_events={signed_b.transfer.event_id():signed_b}; adversary.sync_with(honest_a)
        time.sleep(.1)
        assert honest_a.state.balance("bob")==8 and honest_a.state.balance("carol")==0
        assert honest_b.state.balance("bob")==0 and honest_b.state.balance("carol")==8
        honest_a.sync_with(honest_b); honest_b.sync_with(honest_a); time.sleep(.1)
        assert tx_a in honest_a.events and tx_b in honest_a.events and tx_a in honest_b.events and tx_b in honest_b.events
        assert honest_a.status()==DecisionStatus.CONFLICTED and honest_b.status()==DecisionStatus.CONFLICTED
        assert honest_a.state.balance("bob")==8 and honest_a.state.balance("carol")==0
        assert honest_b.state.balance("bob")==0 and honest_b.state.balance("carol")==8
    finally:
        honest_a.stop(); honest_b.stop(); adversary.stop()
