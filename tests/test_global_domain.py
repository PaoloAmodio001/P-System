from core.event import Transfer
from core.global_domain import (
    GlobalDomain,
    build_global_domain,
)


def test_domain_contains_known_events():
    event = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    domain = build_global_domain(
        [event]
    )

    assert domain.contains(
        event.event_id()
    )


def test_domain_covers_exact_event_set():
    first = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    second = Transfer(
        "carol",
        "dave",
        2,
        0,
    )

    domain = build_global_domain(
        [first, second]
    )

    assert domain.covers(
        [first, second]
    )


def test_domain_rejects_unknown_event():
    known = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    unknown = Transfer(
        "carol",
        "dave",
        2,
        0,
    )

    domain = build_global_domain(
        [known]
    )

    assert domain.covers(
        [known, unknown]
    ) is False


def test_empty_domain_is_valid():
    domain = GlobalDomain(
        event_ids=frozenset()
    )

    assert domain.covers([]) is True
