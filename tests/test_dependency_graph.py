from core.dependency_graph import DependencyGraph
from core.event import Transfer


def test_dependency_graph_tracks_parents():
    first = Transfer("alice", "bob", 4, 0)

    second = Transfer(
        "alice",
        "carol",
        3,
        1,
        parents=(first.event_id(),),
    )

    graph = DependencyGraph.build(
        [first, second]
    )

    assert graph.parents_of(
        first.event_id()
    ) == frozenset()

    assert graph.parents_of(
        second.event_id()
    ) == frozenset({first.event_id()})


def test_dependency_graph_finds_ready_events():
    first = Transfer("alice", "bob", 4, 0)

    second = Transfer(
        "alice",
        "carol",
        3,
        1,
        parents=(first.event_id(),),
    )

    graph = DependencyGraph.build(
        [first, second]
    )

    ready_initial = graph.ready(set())

    assert ready_initial == frozenset({
        first.event_id(),
    })

    ready_after_first = graph.ready({
        first.event_id(),
    })

    assert ready_after_first == frozenset({
        second.event_id(),
    })


def test_missing_parent_is_rejected():
    missing_parent = "0" * 64

    event = Transfer(
        "alice",
        "bob",
        4,
        0,
        parents=(missing_parent,),
    )

    try:
        DependencyGraph.build([event])
    except ValueError as exc:
        assert "UNKNOWN PARENT" in str(exc)
    else:
        raise AssertionError(
            "MISSING PARENT WAS ACCEPTED"
        )


def test_dependency_cycle_is_detected():
    first = Transfer(
        "alice",
        "bob",
        4,
        0,
        parents=("placeholder",),
    )

    second = Transfer(
        "bob",
        "carol",
        2,
        0,
        parents=(first.event_id(),),
    )

    # Reconstruct a valid graph manually to represent
    # a cyclic dependency.
    graph = DependencyGraph({
        first.event_id(): frozenset({
            second.event_id(),
        }),
        second.event_id(): frozenset({
            first.event_id(),
        }),
    })

    assert graph.has_cycle()


def test_acyclic_dependency_graph():
    first = Transfer("alice", "bob", 4, 0)

    second = Transfer(
        "alice",
        "carol",
        3,
        1,
        parents=(first.event_id(),),
    )

    graph = DependencyGraph.build(
        [first, second]
    )

    assert not graph.has_cycle()
