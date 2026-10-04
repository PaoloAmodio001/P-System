from core.conflict_state import ConflictState
from core.decision_status import (
    DecisionStatus,
    classify_decision,
)
from core.event import Transfer
from core.relevance_graph import RelevanceGraph
from core.uncertainty_boundary import analyze_boundary


def test_node_a_can_be_unique_with_partial_knowledge():
    visible = Transfer(
        sender="alice",
        receiver="bob",
        amount=3,
        nonce=0,
    )

    graph = RelevanceGraph.build(
        {
            "nonce:alice": {
                f"event:{visible.event_id()}",
            }
        }
    )

    boundary_a = analyze_boundary(
        {
            "nonce:alice",
            f"event:{visible.event_id()}",
        },
        graph,
    )

    status_a = classify_decision(
        boundary_a
    )

    assert status_a == DecisionStatus.UNIQUE


def test_hidden_relevant_information_makes_node_uncertain():
    visible = Transfer(
        sender="alice",
        receiver="bob",
        amount=3,
        nonce=0,
    )

    hidden = Transfer(
        sender="alice",
        receiver="carol",
        amount=5,
        nonce=0,
    )

    graph = RelevanceGraph.build(
        {
            "nonce:alice": {
                f"event:{visible.event_id()}",
                f"event:{hidden.event_id()}",
            }
        }
    )

    boundary_a = analyze_boundary(
        {
            "nonce:alice",
            f"event:{visible.event_id()}",
        },
        graph,
    )

    status_a = classify_decision(
        boundary_a
    )

    assert status_a == DecisionStatus.UNCERTAIN


def test_reconciliation_can_reveal_conflict():
    visible = Transfer(
        sender="alice",
        receiver="bob",
        amount=3,
        nonce=0,
    )

    hidden = Transfer(
        sender="alice",
        receiver="carol",
        amount=5,
        nonce=0,
    )

    conflict = ConflictState(
        alternatives=(
            visible,
            hidden,
        )
    )

    graph = RelevanceGraph.build({})

    boundary = analyze_boundary(
        {
            "nonce:alice",
        },
        graph,
    )

    status = classify_decision(
        boundary,
        conflict,
    )

    assert status == DecisionStatus.CONFLICTED


def test_conflicted_state_has_no_winner():
    visible = Transfer(
        sender="alice",
        receiver="bob",
        amount=3,
        nonce=0,
    )

    hidden = Transfer(
        sender="alice",
        receiver="carol",
        amount=5,
        nonce=0,
    )

    conflict = ConflictState(
        alternatives=(
            visible,
            hidden,
        )
    )

    assert conflict.is_conflicted()
    assert not conflict.has_winner()


def test_two_nodes_can_converge_on_same_conflicted_status():
    first = Transfer(
        sender="alice",
        receiver="bob",
        amount=3,
        nonce=0,
    )

    second = Transfer(
        sender="alice",
        receiver="carol",
        amount=5,
        nonce=0,
    )

    conflict_a = ConflictState(
        alternatives=(
            first,
            second,
        )
    )

    conflict_b = ConflictState(
        alternatives=(
            second,
            first,
        )
    )

    graph = RelevanceGraph.build({})

    boundary_a = analyze_boundary(
        {"nonce:alice"},
        graph,
    )

    boundary_b = analyze_boundary(
        {"nonce:alice"},
        graph,
    )

    status_a = classify_decision(
        boundary_a,
        conflict_a,
    )

    status_b = classify_decision(
        boundary_b,
        conflict_b,
    )

    assert status_a == DecisionStatus.CONFLICTED
    assert status_b == DecisionStatus.CONFLICTED
    assert status_a == status_b
