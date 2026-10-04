import time
from tests.signed_helpers import authorize, identity_with_claim, signed_transfer
from core.decision_status import DecisionStatus
from core.state import State
from network.node import Node

def test_repeated_sync_is_idempotent():
    nodes=[Node(f"node-{i}",State({"alice":10}),port=0) for i in range(3)]
    for node in nodes: node.start()
    try:
        identity, claim=identity_with_claim("alice")
        for node in nodes: authorize(node,claim)
        tx_a,signed_a=signed_transfer(identity,"alice","bob",8,0)
        tx_b,signed_b=signed_transfer(identity,"alice","carol",8,0)
        assert nodes[0].receive_signed(signed_a,broadcast=False)
        assert nodes[1].receive_signed(signed_b,broadcast=False)
        nodes[0].sync_with(nodes[2]); nodes[1].sync_with(nodes[2])
        deadline=time.time()+2
        while len(nodes[2].events)<2 and time.time()<deadline: time.sleep(.01)
        assert set(nodes[2].events)=={tx_a,tx_b}
        for _ in range(5):
            nodes[0].sync_with(nodes[2]); nodes[1].sync_with(nodes[2]); nodes[2].sync_with(nodes[0]); nodes[2].sync_with(nodes[1])
        time.sleep(.1)
        assert all(len(n.events)==2 for n in nodes)
        assert all(set(n.events)=={tx_a,tx_b} for n in nodes)
        assert all(n.status()==DecisionStatus.CONFLICTED for n in nodes)
    finally:
        for node in nodes: node.stop()
