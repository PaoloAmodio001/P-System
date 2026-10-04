from core.event import Transfer
from core.partial_knowledge import PartialKnowledge
from core.state import State
from core.verifiable_view import build_verifiable_view
from simulator.partition import NetworkPartition


def test_partition_conflict_converges_to_same_ambiguity():
    initial = State(
        balances={"alice": 10},
        nonces={"alice": 0},
    )

    first = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    second = Transfer(
        "alice",
        "carol",
        4,
        0,
    )

    network = NetworkPartition(
        nodes={
            "A": PartialKnowledge(
                events=frozenset({first})
            ),
            "B": PartialKnowledge(
                events=frozenset({second})
            ),
        }
    )

    # Prima della riconciliazione i nodi vedono
    # informazioni diverse.
    view_a_before = build_verifiable_view(
        initial,
        list(network.knowledge("A").events),
    )

    view_b_before = build_verifiable_view(
        initial,
        list(network.knowledge("B").events),
    )

    assert view_a_before.is_unique()
    assert view_b_before.is_unique()

    # Riconciliazione.
    network.reconcile("A", "B")

    events_a = list(
        network.knowledge("A").events
    )

    events_b = list(
        network.knowledge("B").events
    )

    # La conoscenza deve convergere.
    assert (
        network.knowledge("A").events
        == network.knowledge("B").events
    )

    view_a = build_verifiable_view(
        initial,
        events_a,
    )

    view_b = build_verifiable_view(
        initial,
        events_b,
    )

    # Entrambi devono vedere la stessa ambiguità.
    assert view_a.is_ambiguous()
    assert view_b.is_ambiguous()

    assert view_a.has_winner() is False
    assert view_b.has_winner() is False

    assert set(view_a.alternatives()) == {
        first,
        second,
    }

    assert set(view_b.alternatives()) == {
        first,
        second,
    }


def test_reconciliation_does_not_delete_conflicting_events():
    first = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    second = Transfer(
        "alice",
        "carol",
        4,
        0,
    )

    network = NetworkPartition(
        nodes={
            "A": PartialKnowledge(
                events=frozenset({first})
            ),
            "B": PartialKnowledge(
                events=frozenset({second})
            ),
        }
    )

    network.reconcile("A", "B")

    combined = network.knowledge("A").events

    assert first in combined
    assert second in combined
    assert len(combined) == 2
