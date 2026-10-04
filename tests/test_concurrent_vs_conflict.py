from core.conflict_reconciler import ConflictReconciler
from core.conflict_state import ConflictState
from core.event import Transfer


def test_independent_chains_are_not_a_conflict():
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
        parents=(event_a.event_id(),),
    )

    event_c = Transfer(
        "dave",
        "erin",
        4,
        0,
    )

    event_d = Transfer(
        "erin",
        "frank",
        1,
        0,
        parents=(event_c.event_id(),),
    )

    first = ConflictState(
        alternatives=(event_a, event_b)
    )

    second = ConflictState(
        alternatives=(event_c, event_d)
    )

    merged = ConflictReconciler.merge(
        first,
        second,
    )

    assert not merged.is_conflicted()
    assert not merged.has_winner()

    assert set(merged.alternatives) == {
        event_a,
        event_b,
        event_c,
        event_d,
    }


def test_same_nonce_alternatives_are_a_real_conflict():
    event_a = Transfer(
        "alice",
        "bob",
        5,
        0,
    )

    event_b = Transfer(
        "alice",
        "carol",
        4,
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

    assert merged.is_conflicted()
    assert not merged.has_winner()


def test_independent_chain_remains_independent_after_reconciliation():
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
        parents=(event_a.event_id(),),
    )

    event_c = Transfer(
        "dave",
        "erin",
        4,
        0,
    )

    first = ConflictState(
        alternatives=(event_a, event_b)
    )

    second = ConflictState(
        alternatives=(event_c,)
    )

    merged = ConflictReconciler.merge(
        first,
        second,
    )

    assert not merged.is_conflicted()
    assert event_a in merged.alternatives
    assert event_b in merged.alternatives
    assert event_c in merged.alternatives
