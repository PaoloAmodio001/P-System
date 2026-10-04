from core.conflict_state import ConflictState
from core.decision_status import (
    DecisionStatus,
    classify_decision,
)
from core.event import Transfer
from core.relevance_graph import RelevanceGraph
from core.uncertainty_boundary import analyze_boundary


def test_unique_when_no_relevant_uncertainty_exists():
    graph = RelevanceGraph.build({})

    boundary = analyze_boundary(
        {"balance:alice"},
        graph,
    )

    status = classify_decision(
        boundary
    )

    assert status == DecisionStatus.UNIQUE


def test_uncertain_when_relevant_unknown_exists():
    graph = RelevanceGraph.build(
        {
            "balance:alice": {
                "event:hidden"
            }
        }
    )

    boundary = analyze_boundary(
        {"balance:alice"},
        graph,
    )

    status = classify_decision(
        boundary
    )

    assert status == DecisionStatus.UNCERTAIN


def test_conflicted_when_incompatible_alternatives_exist():
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

    conflict = ConflictState(
        alternatives=(first, second)
    )

    graph = RelevanceGraph.build({})

    boundary = analyze_boundary(
        {"nonce:alice"},
        graph,
    )

    status = classify_decision(
        boundary,
        conflict,
    )

    assert status == DecisionStatus.CONFLICTED


def test_conflict_has_priority_over_uncertainty():
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

    conflict = ConflictState(
        alternatives=(first, second)
    )

    graph = RelevanceGraph.build(
        {
            "nonce:alice": {
                "event:hidden"
            }
        }
    )

    boundary = analyze_boundary(
        {"nonce:alice"},
        graph,
    )

    status = classify_decision(
        boundary,
        conflict,
    )

    assert status == DecisionStatus.CONFLICTED


def test_uncertainty_does_not_select_a_winner():
    graph = RelevanceGraph.build(
        {
            "balance:alice": {
                "event:A",
                "event:B",
            }
        }
    )

    boundary = analyze_boundary(
        {"balance:alice"},
        graph,
    )

    status = classify_decision(
        boundary
    )

    assert status == DecisionStatus.UNCERTAIN
