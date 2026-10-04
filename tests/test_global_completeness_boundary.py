from core.decision_status import DecisionStatus
from core.event import Transfer
from core.partial_knowledge import PartialKnowledge
from core.state import State
from network.node import Node


def test_no_parent_missing_is_not_proof_of_global_completeness():
    visible = Transfer(
        "alice",
        "bob",
        5,
        0,
    )

    hidden = Transfer(
        "alice",
        "carol",
        5,
        0,
    )

    knowledge = PartialKnowledge(
        events=frozenset({visible})
    )

    assert knowledge.complete()

    node = Node(
        "node-A",
        State({"alice": 10}),
    )

    assert node.receive(visible)

    # The node has complete causal knowledge of what it knows.
    assert node.status() == DecisionStatus.UNIQUE

    # But there is no global-completeness proof.
    assert hidden not in node.events

    # Once the independent event becomes known, the status changes.
    node.events.append(hidden)

    assert node.status() == DecisionStatus.CONFLICTED
