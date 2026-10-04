from core.causal_closure import (
    build_causal_closure,
    verify_causal_closure,
)
from core.event import Transfer


def test_empty_events_are_causally_closed():
    assert verify_causal_closure([]) is True


def test_event_without_parents_is_closed():
    event = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    assert verify_causal_closure(
        [event]
    ) is True


def test_known_parent_is_closed():
    parent = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    child = Transfer(
        "bob",
        "carol",
        2,
        0,
        parents=(parent.event_id(),),
    )

    assert verify_causal_closure(
        [parent, child]
    ) is True


def test_missing_parent_is_not_closed():
    parent = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    child = Transfer(
        "bob",
        "carol",
        2,
        0,
        parents=(parent.event_id(),),
    )

    assert verify_causal_closure(
        [child]
    ) is False


def test_causal_cycle_is_not_closed():
    first = Transfer(
        "alice",
        "bob",
        3,
        0,
        parents=("future",),
    )

    # Il parent non esistente deve impedire
    # la costruzione della chiusura causale.
    assert verify_causal_closure(
        [first]
    ) is False


def test_build_causal_closure_returns_proof():
    event = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    closure = build_causal_closure(
        [event]
    )

    assert closure is not None
    assert closure.contains(
        event.event_id()
    )


def test_build_causal_closure_fails_for_missing_parent():
    parent = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    child = Transfer(
        "bob",
        "carol",
        2,
        0,
        parents=(parent.event_id(),),
    )

    closure = build_causal_closure(
        [child]
    )

    assert closure is None
