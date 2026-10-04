from core.event import Transfer
from core.state import State
from core.state_view import StateView
from core.verifiable_view import build_verifiable_view
from core.partial_knowledge import PartialKnowledge
from simulator.partition import NetworkPartition


def test_two_nodes_reconcile_to_same_knowledge():
    initial = State(
        balances={
            "alice": 10,
            "carol": 10,
        },
        nonces={
            "alice": 0,
            "carol": 0,
        },
    )

    event_a = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    event_b = Transfer(
        "carol",
        "dave",
        2,
        0,
    )

    network = NetworkPartition(
        nodes={
            "A": PartialKnowledge(
                events=frozenset({event_a})
            ),
            "B": PartialKnowledge(
                events=frozenset({event_b})
            ),
        }
    )

    network.reconcile("A", "B")

    knowledge_a = network.knowledge("A")
    knowledge_b = network.knowledge("B")

    assert knowledge_a.events == knowledge_b.events

    events = list(knowledge_a.events)

    view_a = build_verifiable_view(
        initial,
        events,
    )

    view_b = build_verifiable_view(
        initial,
        events,
    )

    assert view_a.is_unique()
    assert view_b.is_unique()

    assert view_a.state.root() == view_b.state.root()


def test_two_nodes_preserve_same_conflict():
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

    network.reconcile("A", "B")

    events_a = list(
        network.knowledge("A").events
    )

    events_b = list(
        network.knowledge("B").events
    )

    view_a = build_verifiable_view(
        initial,
        events_a,
    )

    view_b = build_verifiable_view(
        initial,
        events_b,
    )

    assert view_a.is_ambiguous()
    assert view_b.is_ambiguous()

    assert not view_a.has_winner()
    assert not view_b.has_winner()


def test_independent_event_survives_conflict():
    initial = State(
        balances={
            "alice": 10,
            "carol": 10,
        },
        nonces={
            "alice": 0,
            "carol": 0,
        },
    )

    conflict_a = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    conflict_b = Transfer(
        "alice",
        "dave",
        4,
        0,
    )

    independent = Transfer(
        "carol",
        "erin",
        2,
        0,
    )

    network = NetworkPartition(
        nodes={
            "A": PartialKnowledge(
                events=frozenset({
                    conflict_a,
                    independent,
                })
            ),
            "B": PartialKnowledge(
                events=frozenset({
                    conflict_b,
                })
            ),
        }
    )

    network.reconcile("A", "B")

    events = list(
        network.knowledge("A").events
    )

    view = build_verifiable_view(
        initial,
        events,
    )

    assert view.is_ambiguous()

    alternatives = view.alternatives()

    assert conflict_a in alternatives
    assert conflict_b in alternatives
    assert independent not in alternatives
