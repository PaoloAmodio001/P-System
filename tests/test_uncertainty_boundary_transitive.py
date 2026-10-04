from core.relevance_graph import RelevanceGraph
from core.uncertainty_boundary import (
    RelevanceStatus,
    analyze_boundary,
)


def test_unknown_transitive_dependency_is_potentially_relevant():
    graph = RelevanceGraph.build(
        {
            "balance:alice": {"event:A"},
            "event:A": {"event:B"},
            "event:B": {"event:C"},
            "event:C": {"event:hidden"},
        }
    )

    boundary = analyze_boundary(
        {"balance:alice"},
        graph,
    )

    assert boundary.status(
        "event:hidden"
    ) == RelevanceStatus.POTENTIALLY_RELEVANT


def test_all_transitive_dependencies_are_reached():
    graph = RelevanceGraph.build(
        {
            "balance:alice": {"event:A"},
            "event:A": {"event:B"},
            "event:B": {"event:C"},
        }
    )

    boundary = analyze_boundary(
        {"balance:alice"},
        graph,
    )

    assert boundary.potentially_relevant == frozenset(
        {
            "event:A",
            "event:B",
            "event:C",
        }
    )


def test_disconnected_region_remains_irrelevant():
    graph = RelevanceGraph.build(
        {
            "balance:alice": {"event:A"},
            "event:A": {"event:B"},
            "balance:carol": {"event:C"},
            "event:C": {"event:D"},
        }
    )

    boundary = analyze_boundary(
        {"balance:alice"},
        graph,
    )

    assert boundary.status(
        "balance:carol"
    ) == RelevanceStatus.IRRELEVANT

    assert boundary.status(
        "event:C"
    ) == RelevanceStatus.IRRELEVANT

    assert boundary.status(
        "event:D"
    ) == RelevanceStatus.IRRELEVANT


def test_known_nodes_are_not_potentially_relevant():
    graph = RelevanceGraph.build(
        {
            "balance:alice": {"event:A"},
            "event:A": {"event:B"},
        }
    )

    boundary = analyze_boundary(
        {
            "balance:alice",
            "event:A",
        },
        graph,
    )

    assert "balance:alice" not in (
        boundary.potentially_relevant
    )

    assert "event:A" not in (
        boundary.potentially_relevant
    )

    assert "event:B" in (
        boundary.potentially_relevant
    )
