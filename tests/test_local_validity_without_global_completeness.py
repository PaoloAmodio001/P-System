from core.decision_status import DecisionStatus
from core.event import Transfer
from core.state import State
from network.node import Node


def test_local_validity_does_not_prove_global_completeness():
    node = Node(
        "node-A",
        State({"alice": 10}),
    )

    tx_known = Transfer(
        "alice",
        "bob",
        5,
        0,
    )

    tx_hidden = Transfer(
        "alice",
        "carol",
        5,
        0,
    )

    # The known event is locally valid.
    assert node.receive(tx_known)

    assert node.state.balance("alice") == 5
    assert node.state.balance("bob") == 5

    # The node has no evidence of a conflict in its current knowledge.
    assert node.status() == DecisionStatus.UNIQUE

    # But UNIQUE must not be interpreted as proof that
    # no relevant event exists elsewhere.
    assert tx_hidden not in node.events

    # When the hidden event becomes known, the classification changes.
    node.events.append(tx_hidden)

    assert node.status() == DecisionStatus.CONFLICTED

    # The previously applied local state remains unchanged.
    assert node.state.balance("alice") == 5
    assert node.state.balance("bob") == 5
    assert node.state.balance("carol") == 0
