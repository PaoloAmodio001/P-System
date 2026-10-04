from core.event import Transfer
from core.precedence import PrecedenceAttestation
from core.precedence_graph import PrecedenceGraph
from crypto.identity import Identity


def test_precedence_graph_tracks_transitive_order():
    identity = Identity.create()

    event_a = Transfer("alice", "bob", 5, 0)
    event_b = Transfer("bob", "carol", 3, 0)
    event_c = Transfer("carol", "dave", 2, 0)

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
            event_b.event_id(),
            event_c.event_id(),
        )
    )

    assert graph.reachable(
        event_a.event_id(),
        event_b.event_id(),
    )

    assert graph.reachable(
        event_a.event_id(),
        event_c.event_id(),
    )


def test_precedence_graph_detects_concurrency():
    identity = Identity.create()

    event_a = Transfer("alice", "bob", 5, 0)
    event_b = Transfer("carol", "dave", 3, 0)

    graph = PrecedenceGraph()

    assert graph.concurrent(
        event_a.event_id(),
        event_b.event_id(),
    )

    graph.add(
        PrecedenceAttestation.create(
            identity,
            event_a.event_id(),
            event_b.event_id(),
        )
    )

    assert not graph.concurrent(
        event_a.event_id(),
        event_b.event_id(),
    )


def test_precedence_graph_detects_cycle():
    identity = Identity.create()

    event_a = Transfer("alice", "bob", 5, 0)
    event_b = Transfer("carol", "dave", 3, 0)

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
            event_b.event_id(),
            event_a.event_id(),
        )
    )

    assert graph.has_cycle()
