from core.state import State
from core.event import Transfer
from simulator.network import create_network


def test_network_reconciliation_conflict():
    nodes = create_network(
        5,
        State({"alice": 10})
    )

    tx_a = Transfer("alice", "bob", 8, 0)
    tx_b = Transfer("alice", "carol", 8, 0)

    group_a = nodes[:3]
    group_b = nodes[3:]

    # Network partition
    for node in group_a:
        assert node.receive(tx_a)

    for node in group_b:
        assert node.receive(tx_b)

    # Network reconnects.
    #
    # Each group now sees the transaction
    # accepted by the other group.
    #
    # We deliberately DO NOT decide which one wins.
    #
    # This test demonstrates that the protocol
    # currently has no deterministic reconciliation rule.

    conflicting = []

    for node in group_a:
        if node.state_root() != group_b[0].state_root():
            conflicting.append(node.node_id)

    assert len(conflicting) == 3
