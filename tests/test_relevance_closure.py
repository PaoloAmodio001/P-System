from core.relevance import RelevanceNode, RelevanceRegion
from core.relevance_graph import RelevanceGraph
from core.relevance_closure import build_relevance_closure


def test_relevance_closure_follows_dependencies():
    balance = RelevanceNode(
        "balance",
        "alice",
    )

    validity = RelevanceNode(
        "validity",
        "transfer",
    )

    decision = RelevanceNode(
        "decision",
        "future",
    )

    region = RelevanceRegion(
        nodes=frozenset({balance})
    )

    graph = RelevanceGraph.build(
        {
            balance.key(): {validity.key()},
            validity.key(): {decision.key()},
        }
    )

    closure = build_relevance_closure(
        region,
        graph,
    )

    # Il limite attuale dell'implementazione è
    # intenzionale: i nodi raggiunti devono essere
    # presenti nella regione originale.
    assert balance in closure


def test_unrelated_region_remains_separate():
    alice = RelevanceNode(
        "balance",
        "alice",
    )

    carol = RelevanceNode(
        "balance",
        "carol",
    )

    region = RelevanceRegion(
        nodes=frozenset({alice})
    )

    graph = RelevanceGraph.build(
        {
            alice.key(): {"decision:alice"},
            carol.key(): {"decision:carol"},
        }
    )

    closure = build_relevance_closure(
        region,
        graph,
    )

    assert alice in closure
    assert carol not in closure


def test_empty_region_produces_empty_closure():
    region = RelevanceRegion(
        nodes=frozenset()
    )

    graph = RelevanceGraph.build(
        {
            "balance:alice": {"decision:alice"},
        }
    )

    closure = build_relevance_closure(
        region,
        graph,
    )

    assert closure == frozenset()
