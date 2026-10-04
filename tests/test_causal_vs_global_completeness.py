from core.decision_status import DecisionStatus
from core.event import Transfer
from core.partial_knowledge import PartialKnowledge
from core.state import State
from network.node import Node


def test_complete_causal_history_does_not_prove_global_completeness():
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

    # No declared parent is missing.
    assert knowledge.complete()
    assert not knowledge.missing_parents()

    node = Node(
        "node-A",
        State({"alice": 10}),
    )

    assert node.receive(visible)
    assert node.status() == DecisionStatus.UNIQUE

    # The hidden concurrent event has no missing parent either.
    assert hidden.parents == ()
    assert hidden not in node.events

    # Therefore causal completeness alone cannot prove
    # global completeness.
    node.events.append(hidden)

    assert node.status() == DecisionStatus.CONFLICTED

    # The locally applied state is preserved.
    assert node.state.balance("alice") == 5
    assert node.state.balance("bob") == 5
    assert node.state.balance("carol") == 0
