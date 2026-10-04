from core.event import Transfer
from core.partial_knowledge import PartialKnowledge


def test_partial_knowledge_can_be_incomplete():
    first = Transfer(
        "alice",
        "bob",
        4,
        0,
    )

    second = Transfer(
        "alice",
        "carol",
        3,
        1,
        parents=(first.event_id(),),
    )

    knowledge = PartialKnowledge(
        events=frozenset({second})
    )

    assert not knowledge.complete()

    assert knowledge.missing_parents() == frozenset({
        first.event_id(),
    })


def test_partial_knowledge_can_be_complete():
    first = Transfer(
        "alice",
        "bob",
        4,
        0,
    )

    second = Transfer(
        "alice",
        "carol",
        3,
        1,
        parents=(first.event_id(),),
    )

    knowledge = PartialKnowledge(
        events=frozenset({
            first,
            second,
        })
    )

    assert knowledge.complete()
    assert not knowledge.missing_parents()


def test_partial_knowledge_merge():
    first = Transfer(
        "alice",
        "bob",
        4,
        0,
    )

    second = Transfer(
        "bob",
        "carol",
        2,
        0,
    )

    node_a = PartialKnowledge(
        events=frozenset({first})
    )

    node_b = PartialKnowledge(
        events=frozenset({second})
    )

    merged = node_a.merge(node_b)

    assert merged.event_ids() == frozenset({
        first.event_id(),
        second.event_id(),
    })


def test_merge_is_idempotent():
    first = Transfer(
        "alice",
        "bob",
        4,
        0,
    )

    knowledge = PartialKnowledge(
        events=frozenset({first})
    )

    merged = knowledge.merge(knowledge)

    assert merged == knowledge
