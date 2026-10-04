from core.relevance_graph import RelevanceGraph


def test_graph_represents_property_dependencies():
    graph = RelevanceGraph.build(
        {
            "alice.balance": {"transfer.validity"},
            "alice.nonce": {"transfer.validity"},
            "transfer.validity": {"future.decision"},
        }
    )

    assert graph.successors(
        "alice.balance"
    ) == frozenset({"transfer.validity"})

    assert graph.successors(
        "alice.nonce"
    ) == frozenset({"transfer.validity"})


def test_graph_finds_transitive_relevance():
    graph = RelevanceGraph.build(
        {
            "alice.balance": {"transfer.validity"},
            "alice.nonce": {"transfer.validity"},
            "transfer.validity": {"future.decision"},
        }
    )

    assert graph.reachable(
        "alice.balance",
        "future.decision",
    )

    assert graph.reachable(
        "alice.nonce",
        "future.decision",
    )


def test_closure_follows_all_dependencies():
    graph = RelevanceGraph.build(
        {
            "alice.balance": {"transfer.validity"},
            "alice.nonce": {"transfer.validity"},
            "transfer.validity": {"future.decision"},
        }
    )

    closure = graph.closure(
        {"alice.balance"}
    )

    assert closure == frozenset(
        {
            "alice.balance",
            "transfer.validity",
            "future.decision",
        }
    )


def test_unrelated_property_is_outside_closure():
    graph = RelevanceGraph.build(
        {
            "alice.balance": {"transfer.validity"},
            "alice.nonce": {"transfer.validity"},
            "transfer.validity": {"future.decision"},
            "carol.balance": {"carol.decision"},
        }
    )

    closure = graph.closure(
        {"alice.balance"}
    )

    assert "carol.balance" not in closure
    assert "carol.decision" not in closure


def test_closure_is_transitive_and_deterministic():
    graph = RelevanceGraph.build(
        {
            "a": {"b"},
            "b": {"c"},
            "c": {"d"},
        }
    )

    first = graph.closure({"a"})
    second = graph.closure({"a"})

    assert first == second

    assert first == frozenset(
        {"a", "b", "c", "d"}
    )
