from core.decision_status import DecisionStatus
from core.event import Transfer
from core.state import State
from network.node import Node
from network.reconciliation import reconcile


def test_inconsistent_dissemination_cannot_create_unique_state():
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

    # Different nodes initially receive different alternatives.
    assert node_a.receive(tx_a)
    assert node_b.receive(tx_b)

    # Node C initially knows neither alternative.
    assert node_c.status() == DecisionStatus.UNIQUE

    # Reconciliation exposes the incompatible knowledge.
    reconcile(node_a, node_c)
    reconcile(node_b, node_c)

    assert set(node_c.events) == {
        tx_a,
        tx_b,
    }

    assert node_c.status() == DecisionStatus.CONFLICTED

    # Once the conflicting knowledge is exchanged,
    # neither original node may remain UNIQUE.
    reconcile(node_a, node_b)

    assert set(node_a.events) == {
        tx_a,
        tx_b,
    }

    assert set(node_b.events) == {
        tx_a,
        tx_b,
    }

    assert node_a.status() == DecisionStatus.CONFLICTED
    assert node_b.status() == DecisionStatus.CONFLICTED
