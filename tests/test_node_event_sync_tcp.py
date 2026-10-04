import time
from tests.signed_helpers import authorize, identity_with_claim, signed_transfer
from core.state import State
from network.node import Node

def test_node_syncs_events_over_tcp():
    node_a=Node("node-A", State({"alice":10}), port=0)
    node_b=Node("node-B", State({"alice":10}), port=0)
    node_a.start(); node_b.start()
    try:
        identity, claim=identity_with_claim("alice")
        authorize(node_a, claim); authorize(node_b, claim)
        tx, signed=signed_transfer(identity,"alice","bob",4,0)
        assert node_a.receive_signed(signed,broadcast=False)
        node_a.sync_with(node_b)
        deadline=time.time()+2
        while tx not in node_b.events and time.time()<deadline: time.sleep(.01)
        assert tx in node_b.events
        assert node_b.state.balance("alice")==6
        assert node_b.state.balance("bob")==4
        assert node_b.state.nonce("alice")==1
    finally:
        node_a.stop(); node_b.stop()
