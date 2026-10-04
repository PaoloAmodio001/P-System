from core.decision_status import DecisionStatus
from core.event import Transfer
from core.partial_knowledge import PartialKnowledge
from core.state import State
from network.node import Node


def test_causal_completeness_does_not_prove_decision_invariance():
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

    # The visible causal history is complete.
    assert knowledge.complete()

    node = Node(
        "node-A",
        State({"alice": 10}),
    )

    assert node.receive(visible)

    # Locally the decision appears unique.
    before = node.status()
    assert before == DecisionStatus.UNIQUE

    # But causal completeness did not establish invariance.
    node.events.append(hidden)

    after = node.status()

    assert after == DecisionStatus.CONFLICTED
    assert after != before
