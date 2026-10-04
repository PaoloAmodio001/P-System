from core.event import Transfer
from core.execution_relation import (
    ExecutionRelation,
    classify_execution_relation,
)


def test_causal_relation_has_priority():
    first = Transfer("alice", "bob", 3, 0)

    second = Transfer(
        "bob",
        "carol",
        2,
        0,
        parents=(first.event_id(),),
    )

    events = [first, second]

    assert classify_execution_relation(
        first,
        second,
        events,
    ) == ExecutionRelation.CAUSAL


def test_independent_events_are_parallel():
    first = Transfer("alice", "bob", 3, 0)
    second = Transfer("carol", "dave", 2, 0)

    events = [first, second]

    assert classify_execution_relation(
        first,
        second,
        events,
    ) == ExecutionRelation.PARALLEL


def test_same_sender_same_nonce_is_conflict():
    first = Transfer("alice", "bob", 3, 0)
    second = Transfer("alice", "carol", 4, 0)

    events = [first, second]

    assert classify_execution_relation(
        first,
        second,
        events,
    ) == ExecutionRelation.CONFLICT


def test_reverse_causal_relation_is_detected():
    first = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    second = Transfer(
        "bob",
        "carol",
        2,
        0,
        parents=(first.event_id(),),
    )

    events = [first, second]

    assert classify_execution_relation(
        second,
        first,
        events,
    ) == ExecutionRelation.CAUSAL
