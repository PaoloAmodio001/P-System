from core.event import Transfer
from core.state import State
from core.partial_knowledge import PartialKnowledge
from core.verifiable_view import build_verifiable_view


def test_different_knowledge_produces_different_views():
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

    knowledge_a = PartialKnowledge(
        events=frozenset({event_a})
    )

    knowledge_b = PartialKnowledge(
        events=frozenset({event_b})
    )

    view_a = build_verifiable_view(
        initial,
        list(knowledge_a.events),
    )

    view_b = build_verifiable_view(
        initial,
        list(knowledge_b.events),
    )

    assert view_a.is_unique()
    assert view_b.is_unique()

    assert view_a.state.root() != view_b.state.root()


def test_nodes_do_not_claim_convergence_before_reconciliation():
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

    view_a = build_verifiable_view(
        initial,
        [event_a],
    )

    view_b = build_verifiable_view(
        initial,
        [event_b],
    )

    assert view_a.state.root() != view_b.state.root()


def test_reconciliation_restores_same_knowledge():
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

    knowledge_a = PartialKnowledge(
        events=frozenset({event_a})
    )

    knowledge_b = PartialKnowledge(
        events=frozenset({event_b})
    )

    merged = knowledge_a.merge(
        knowledge_b
    )

    view_a = build_verifiable_view(
        initial,
        list(merged.events),
    )

    view_b = build_verifiable_view(
        initial,
        list(merged.events),
    )

    assert view_a.is_unique()
    assert view_b.is_unique()

    assert view_a.state.root() == view_b.state.root()
