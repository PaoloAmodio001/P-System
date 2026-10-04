from core.dependency_closure import (
    build_dependency_closure,
    verify_dependency_closure,
)
from core.event import Transfer


def test_event_without_dependencies_is_closed():
    event = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    assert verify_dependency_closure(
        [event]
    ) is True


def test_known_dependency_is_closed():
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

    assert verify_dependency_closure(
        [parent, child]
    ) is True


def test_missing_dependency_is_not_closed():
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

    assert verify_dependency_closure(
        [child]
    ) is False


def test_dependency_cycle_is_not_closed():
    first = Transfer(
        "alice",
        "bob",
        3,
        0,
        parents=("missing",),
    )

    assert verify_dependency_closure(
        [first]
    ) is False


def test_build_dependency_closure():
    event = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    closure = build_dependency_closure(
        [event]
    )

    assert closure is not None
    assert closure.contains(
        event.event_id()
    )


def test_build_dependency_closure_fails_for_missing_dependency():
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

    closure = build_dependency_closure(
        [child]
    )

    assert closure is None
