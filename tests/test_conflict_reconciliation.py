from core.conflict_state import ConflictState
from core.event import Transfer
from core.state_view import StateView


def test_nodes_converge_to_same_ambiguous_view_after_reconciliation():
    conflict_a = Transfer(
        "alice",
        "bob",
        6,
        0,
    )

    conflict_b = Transfer(
        "alice",
        "carol",
        7,
        0,
    )

    node_a_view = StateView.ambiguous(
        ConflictState(
            alternatives=(conflict_a,)
        )
    )

    node_b_view = StateView.ambiguous(
        ConflictState(
            alternatives=(conflict_b,)
        )
    )

    merged = ConflictState(
        alternatives=(
            conflict_a,
            conflict_b,
        )
    )

    reconciled_a = StateView.ambiguous(merged)
    reconciled_b = StateView.ambiguous(merged)

    assert node_a_view.is_ambiguous()
    assert node_b_view.is_ambiguous()

    assert reconciled_a.is_ambiguous()
    assert reconciled_b.is_ambiguous()

    assert reconciled_a.alternatives() == reconciled_b.alternatives()

    assert conflict_a in reconciled_a.alternatives()
    assert conflict_b in reconciled_a.alternatives()

    assert not reconciled_a.has_winner()
    assert not reconciled_b.has_winner()


def test_conflict_reconciler_merges_alternatives():
    from core.conflict_reconciler import ConflictReconciler

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

    merged = ConflictReconciler.merge(
        first,
        second,
    )

    assert merged.alternatives == (
        event_a,
        event_b,
    )

    assert merged.is_conflicted()
    assert not merged.has_winner()


def test_conflict_reconciler_deduplicates_events():
    from core.conflict_reconciler import ConflictReconciler

    event_a = Transfer(
        "alice",
        "bob",
        6,
        0,
    )

    first = ConflictState(
        alternatives=(event_a,)
    )

    second = ConflictState(
        alternatives=(event_a,)
    )

    merged = ConflictReconciler.merge(
        first,
        second,
    )

    assert merged.alternatives == (
        event_a,
    )

    assert not merged.is_conflicted()
    assert not merged.has_winner()
