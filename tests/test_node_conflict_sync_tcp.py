import time
from tests.signed_helpers import authorize, identity_with_claim, signed_transfer
from core.conflict_state import ConflictState
from core.state import State
from network.conflicted_state import ConflictedState
from network.node import Node

def test_conflicting_events_sync_over_tcp_without_winner():
    node_a=Node("node-A",State({"alice":10}),port=0); node_b=Node("node-B",State({"alice":10}),port=0)
    node_a.start(); node_b.start()
    try:
        identity,claim=identity_with_claim("alice"); authorize(node_a,claim); authorize(node_b,claim)
        tx_a,signed_a=signed_transfer(identity,"alice","bob",8,0); tx_b,signed_b=signed_transfer(identity,"alice","carol",8,0)
        assert node_a.receive_signed(signed_a,broadcast=False); assert node_b.receive_signed(signed_b,broadcast=False)
        assert node_a.state_root()!=node_b.state_root()
        node_a.sync_with(node_b); node_b.sync_with(node_a)
        deadline=time.time()+2
        while (tx_a not in node_a.events or tx_b not in node_a.events or tx_a not in node_b.events or tx_b not in node_b.events) and time.time()<deadline: time.sleep(.01)
        assert set(node_a.events)=={tx_a,tx_b} and set(node_b.events)=={tx_a,tx_b}
        assert node_a.state_root()!=node_b.state_root()
        conflict=ConflictState(tuple(sorted([tx_a,tx_b],key=lambda e:e.event_id())))
        conflicted_a=ConflictedState(base_state=node_a.state,alternatives=conflict); conflicted_b=ConflictedState(base_state=node_b.state,alternatives=conflict)
        assert conflicted_a.is_conflicted and conflicted_b.is_conflicted and not conflicted_a.has_winner and not conflicted_b.has_winner
    finally: node_a.stop(); node_b.stop()
