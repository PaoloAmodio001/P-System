from core.event import Transfer
from core.precedence import PrecedenceAttestation
from core.precedence_graph import PrecedenceGraph
from core.graph_resolution import GraphResolver
from crypto.identity import Identity


def test_graph_resolution_preserves_independent_events():
    identity = Identity.create()

    event_a = Transfer(
        "alice",
        "bob",
        5,
        0,
    )

    event_b = Transfer(
        "bob",
        "carol",
        2,
        0,
    )

    event_c = Transfer(
        "alice",
        "dave",
        3,
        1,
        parents=(event_a.event_id(),),
    )

    graph = PrecedenceGraph()

    graph.add(
        PrecedenceAttestation.create(
            identity,
            event_a.event_id(),
            event_b.event_id(),
        )
    )

    graph.add(
        PrecedenceAttestation.create(
            identity,
            event_a.event_id(),
            event_c.event_id(),
        )
    )

    resolved = GraphResolver.resolve(
        [event_a, event_b, event_c],
        graph,
    )

    resolved_ids = {
        event.event_id()
        for event in resolved
    }

    assert resolved_ids == {
        event_a.event_id(),
        event_b.event_id(),
        event_c.event_id(),
    }


def test_graph_resolution_rejects_conflicting_events():
    identity = Identity.create()

    event_a = Transfer(
        "alice",
        "bob",
        5,
        0,
    )

    event_b = Transfer(
        "alice",
        "carol",
        5,
        0,
    )

    graph = PrecedenceGraph()

    graph.add(
        PrecedenceAttestation.create(
            identity,
            event_a.event_id(),
            event_b.event_id(),
        )
    )

    try:
        GraphResolver.resolve(
            [event_a, event_b],
            graph,
        )
    except ValueError as exc:
        assert str(exc) == "CONFLICTING EVENTS"
    else:
        raise AssertionError(
            "CONFLICTING EVENTS WERE ACCEPTED"
        )
