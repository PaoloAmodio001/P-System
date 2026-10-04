from core.decision_status import DecisionStatus
from core.event import Transfer
from core.state import State
from network.node import Node


def test_hidden_conflict_changes_status_from_unique_to_conflicted():
    node = Node(
        "node-A",
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

    # With only tx_a known, the node has no detected conflict.
    assert node.receive(tx_a)
    assert node.status() == DecisionStatus.UNIQUE

    # tx_b was previously unknown.
    # It is now learned through synchronization.
    node.events.append(tx_b)

    # Knowledge changed, therefore the classification changes.
    assert node.status() == DecisionStatus.CONFLICTED

    # The original local state is not overwritten by the
    # newly discovered conflicting alternative.
    assert node.state.balance("bob") == 8
    assert node.state.balance("carol") == 0
    assert node.state.balance("alice") == 2
