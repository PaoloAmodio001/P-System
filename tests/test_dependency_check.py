from core.dependency_check import depends_on
from core.event import Transfer


def test_direct_dependency():
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

    events = [event_a, event_b]

    assert depends_on(
        event_b,
        event_a.event_id(),
        events,
    )


def test_transitive_dependency():
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
        "carol",
        "dave",
        1,
        0,
        parents=(event_b.event_id(),),
    )

    events = [event_a, event_b, event_c]

    assert depends_on(
        event_c,
        event_a.event_id(),
        events,
    )


def test_independent_event_has_no_dependency():
    event_a = Transfer(
        "alice",
        "bob",
        5,
        0,
    )

    event_b = Transfer(
        "dave",
        "erin",
        2,
        0,
    )

    events = [event_a, event_b]

    assert not depends_on(
        event_b,
        event_a.event_id(),
        events,
    )
