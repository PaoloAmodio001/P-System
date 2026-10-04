import time
from tests.signed_helpers import authorize, identity_with_claim, signed_transfer
from core.decision_status import DecisionStatus
from core.state import State
from network.node import Node

def test_nodes_become_conflicted_after_tcp_sync():
    node_a=Node("node-A",State({"alice":10}),port=0); node_b=Node("node-B",State({"alice":10}),port=0)
    node_a.start(); node_b.start()
    try:
        identity,claim=identity_with_claim("alice"); authorize(node_a,claim); authorize(node_b,claim)
        tx_a,signed_a=signed_transfer(identity,"alice","bob",8,0); tx_b,signed_b=signed_transfer(identity,"alice","carol",8,0)
        assert node_a.receive_signed(signed_a,broadcast=False); assert node_b.receive_signed(signed_b,broadcast=False)
        assert node_a.status()==DecisionStatus.UNIQUE and node_b.status()==DecisionStatus.UNIQUE
        node_a.sync_with(node_b); node_b.sync_with(node_a)
        deadline=time.time()+2
        while (len(node_a.events)<2 or len(node_b.events)<2) and time.time()<deadline: time.sleep(.01)
        assert set(node_a.events)=={tx_a,tx_b} and set(node_b.events)=={tx_a,tx_b}
        assert node_a.status()==DecisionStatus.CONFLICTED and node_b.status()==DecisionStatus.CONFLICTED
    finally: node_a.stop(); node_b.stop()
