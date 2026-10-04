import time
from tests.signed_helpers import authorize, identity_with_claim, signed_transfer
from core.decision_status import DecisionStatus
from core.state import State
from network.node import Node

def test_conflict_status_is_independent_of_sync_order_and_duplicates():
    node_a=Node("node-A",State({"alice":10})); node_b=Node("node-B",State({"alice":10}))
    try:
        node_a.start(); node_b.start()
        identity,claim=identity_with_claim("alice"); authorize(node_a,claim); authorize(node_b,claim)
        tx_a,signed_a=signed_transfer(identity,"alice","bob",8,0); tx_b,signed_b=signed_transfer(identity,"alice","carol",8,0)
        assert node_a.receive_signed(signed_a,broadcast=False); assert node_b.receive_signed(signed_b,broadcast=False)
        node_a.sync_with(node_b); time.sleep(.05); node_b.sync_with(node_a); node_a.sync_with(node_b); node_b.sync_with(node_a); time.sleep(.1)
        assert node_a.status()==DecisionStatus.CONFLICTED and node_b.status()==DecisionStatus.CONFLICTED
        assert set(node_a.events)=={tx_a,tx_b} and set(node_b.events)=={tx_a,tx_b}
        assert node_a.state.balance("alice")==2 and node_a.state.balance("bob")==8 and node_a.state.balance("carol")==0
        assert node_b.state.balance("alice")==2 and node_b.state.balance("bob")==0 and node_b.state.balance("carol")==8
    finally:
        node_a.stop(); node_b.stop()
