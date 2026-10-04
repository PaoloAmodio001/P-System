from core.decision_status import DecisionStatus
from core.event import Transfer
from core.state import State
from network.node import Node


def test_sync_order_does_not_change_conflict_status():
    tx_a = Transfer(
        "alice",
        "bob",
        8,
        0,
    )

    tx_b = Transfer(
        "alice",
        "carol",
        8,
        0,
    )

    node_a = Node(
        "node-A",
        State({"alice": 10}),
    )

    node_b = Node(
        "node-B",
        State({"alice": 10}),
    )

    node_c = Node(
        "node-C",
        State({"alice": 10}),
    )

    # Same knowledge, different arrival order.
    node_a.receive(tx_a)
    node_a.events.append(tx_b)

    node_b.receive(tx_b)
    node_b.events.append(tx_a)

    node_c.receive(tx_a)
    node_c.events.append(tx_b)
    node_c.events.append(tx_a)

    assert set(node_a.events) == {tx_a, tx_b}
    assert set(node_b.events) == {tx_a, tx_b}
    assert set(node_c.events) == {tx_a, tx_b}

    assert node_a.status() == DecisionStatus.CONFLICTED
    assert node_b.status() == DecisionStatus.CONFLICTED
    assert node_c.status() == DecisionStatus.CONFLICTED
