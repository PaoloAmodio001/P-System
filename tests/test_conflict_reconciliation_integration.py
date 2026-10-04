from core.conflict_reconciler import ConflictReconciler
from core.conflict_state import ConflictState
from core.event import Transfer
from core.partial_knowledge import PartialKnowledge
from core.state_view import StateView


def test_partial_knowledge_reconciliation_creates_same_conflict_state():
    event_a = Transfer(
        "alice",
        "bob",
        6,
        0,
    )

    event_b = Transfer(
        "alice",
        "carol",
        7,
        0,
    )

    node_a = PartialKnowledge(
        events=frozenset({event_a})
    )

    node_b = PartialKnowledge(
        events=frozenset({event_b})
    )

    conflicts_a = ConflictState(
        alternatives=tuple(node_a.events)
    )

    conflicts_b = ConflictState(
        alternatives=tuple(node_b.events)
    )

    merged = ConflictReconciler.merge(
        conflicts_a,
        conflicts_b,
    )

    view_a = StateView.ambiguous(merged)
    view_b = StateView.ambiguous(merged)

    assert view_a.is_ambiguous()
    assert view_b.is_ambiguous()

    assert view_a.alternatives() == view_b.alternatives()

    assert event_a in view_a.alternatives()
    assert event_b in view_a.alternatives()

    assert not view_a.has_winner()
    assert not view_b.has_winner()


def test_conflict_merge_is_commutative():
    event_a = Transfer(
        "alice",
        "bob",
        6,
        0,
    )

    event_b = Transfer(
        "alice",
        "carol",
        7,
        0,
    )

    first = ConflictState(
        alternatives=(event_a,)
    )

    second = ConflictState(
        alternatives=(event_b,)
    )

    merged_ab = ConflictReconciler.merge(
        first,
        second,
    )

    merged_ba = ConflictReconciler.merge(
        second,
        first,
    )

    assert set(merged_ab.alternatives) == set(
        merged_ba.alternatives
    )


def test_conflict_merge_is_idempotent():
    event_a = Transfer(
        "alice",
        "bob",
        6,
        0,
    )

    state = ConflictState(
        alternatives=(event_a,)
    )

    merged = ConflictReconciler.merge(
        state,
        state,
    )

    assert merged.alternatives == state.alternatives
    assert not merged.has_winner()


def test_repeated_reconciliation_does_not_create_duplicates():
    event_a = Transfer(
        "alice",
        "bob",
        6,
        0,
    )

    event_b = Transfer(
        "alice",
        "carol",
        7,
        0,
    )

    first = ConflictState(
        alternatives=(event_a,)
    )

    second = ConflictState(
        alternatives=(event_b,)
    )

    merged_once = ConflictReconciler.merge(
        first,
        second,
    )

    merged_twice = ConflictReconciler.merge(
        merged_once,
        second,
    )

    assert set(merged_twice.alternatives) == {
        event_a,
        event_b,
    }

    assert len(merged_twice.alternatives) == 2
    assert not merged_twice.has_winner()


def test_multi_node_reconciliation_converges_independent_of_merge_order():
    event_a = Transfer(
        "alice",
        "bob",
        6,
        0,
    )

    event_b = Transfer(
        "alice",
        "carol",
        7,
        0,
    )

    event_c = Transfer(
        "alice",
        "dave",
        8,
        0,
    )

    state_a = ConflictState(
        alternatives=(event_a,)
    )

    state_b = ConflictState(
        alternatives=(event_b,)
    )

    state_c = ConflictState(
        alternatives=(event_c,)
    )

    # Nodo 1: ((A + B) + C)
    node_1 = ConflictReconciler.merge(
        ConflictReconciler.merge(
            state_a,
            state_b,
        ),
        state_c,
    )

    # Nodo 2: ((C + A) + B)
    node_2 = ConflictReconciler.merge(
        ConflictReconciler.merge(
            state_c,
            state_a,
        ),
        state_b,
    )

    # Nodo 3: ((B + C) + A)
    node_3 = ConflictReconciler.merge(
        ConflictReconciler.merge(
            state_b,
            state_c,
        ),
        state_a,
    )

    assert set(node_1.alternatives) == {
        event_a,
        event_b,
        event_c,
    }

    assert set(node_2.alternatives) == {
        event_a,
        event_b,
        event_c,
    }

    assert set(node_3.alternatives) == {
        event_a,
        event_b,
        event_c,
    }

    assert set(node_1.alternatives) == set(node_2.alternatives)
    assert set(node_2.alternatives) == set(node_3.alternatives)

    assert node_1.is_conflicted()
    assert node_2.is_conflicted()
    assert node_3.is_conflicted()

    assert not node_1.has_winner()
    assert not node_2.has_winner()
    assert not node_3.has_winner()
