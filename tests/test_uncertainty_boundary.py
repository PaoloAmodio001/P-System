from core.relevance_graph import RelevanceGraph
from core.uncertainty_boundary import (
    RelevanceStatus,
    analyze_boundary,
)


def test_unknown_dependency_is_potentially_relevant():
    graph = RelevanceGraph.build(
        {
            "balance:alice": {
                "event:unknown"
            }
        }
    )

    boundary = analyze_boundary(
        {"balance:alice"},
        graph,
    )

    assert boundary.status(
        "event:unknown"
    ) == RelevanceStatus.POTENTIALLY_RELEVANT


def test_known_node_is_known():
    graph = RelevanceGraph.build(
        {
            "balance:alice": {
                "event:unknown"
            }
        }
    )

    boundary = analyze_boundary(
        {"balance:alice"},
        graph,
    )

    assert boundary.status(
        "balance:alice"
    ) == RelevanceStatus.KNOWN


def test_unconnected_node_can_be_irrelevant():
    graph = RelevanceGraph.build(
        {
            "balance:alice": {
                "event:alice"
            },
            "balance:carol": {
                "event:carol"
            },
        }
    )

    boundary = analyze_boundary(
        {"balance:alice"},
        graph,
    )

    assert boundary.status(
        "balance:carol"
    ) == RelevanceStatus.IRRELEVANT


def test_missing_information_is_not_treated_as_irrelevant():
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

    assert "event:hidden" in (
        boundary.potentially_relevant
    )

    assert "event:hidden" not in (
        boundary.irrelevant
    )
