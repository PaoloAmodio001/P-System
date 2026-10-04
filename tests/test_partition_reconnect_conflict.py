import time
from tests.signed_helpers import authorize, identity_with_claim, signed_transfer
from core.decision_status import DecisionStatus
from core.state import State
from network.node import Node

def test_partition_reconnect_preserves_both_conflicting_alternatives():
    node_a=Node("node-A",State({"alice":10})); node_b=Node("node-B",State({"alice":10}))
    try:
        node_a.start(); node_b.start(); identity,claim=identity_with_claim("alice"); authorize(node_a,claim); authorize(node_b,claim)
        tx_a,signed_a=signed_transfer(identity,"alice","bob",8,0); tx_b,signed_b=signed_transfer(identity,"alice","carol",8,0)
        assert node_a.receive_signed(signed_a,broadcast=False); assert node_b.receive_signed(signed_b,broadcast=False)
        assert node_a.status()==DecisionStatus.UNIQUE and node_b.status()==DecisionStatus.UNIQUE
        node_a.sync_with(node_b); node_b.sync_with(node_a); time.sleep(.1)
        assert tx_a in node_a.events and tx_b in node_a.events and tx_a in node_b.events and tx_b in node_b.events
        assert node_a.status()==DecisionStatus.CONFLICTED and node_b.status()==DecisionStatus.CONFLICTED
        assert node_a.state.balance("bob")==8 and node_a.state.balance("carol")==0
        assert node_b.state.balance("bob")==0 and node_b.state.balance("carol")==8
        assert node_a.state.balance("alice")==2 and node_b.state.balance("alice")==2
    finally: node_a.stop(); node_b.stop()
