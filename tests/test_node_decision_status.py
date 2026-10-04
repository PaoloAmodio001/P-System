from core.conflict_state import ConflictState
from core.decision_status import DecisionStatus, classify_decision
from core.event import Transfer
from core.state import State
from core.uncertainty_boundary import UncertaintyBoundary
from network.conflicted_state import ConflictedState
from network.node import Node


def test_node_conflicting_knowledge_is_classified_as_conflicted():
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

    assert node.receive(tx_a)

    node.events.append(tx_b)

    conflict = ConflictState(
        tuple(sorted(
            [tx_a, tx_b],
            key=lambda event: event.event_id(),
        ))
    )

    conflicted = ConflictedState(
        base_state=node.state,
        alternatives=conflict,
    )

    boundary = UncertaintyBoundary(
        known=frozenset(),
        potentially_relevant=frozenset(),
        irrelevant=frozenset(),
    )

    status = classify_decision(
        boundary,
        conflicted.alternatives,
    )

    assert status == DecisionStatus.CONFLICTED
