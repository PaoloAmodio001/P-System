from core.conflict_state import ConflictState
from core.event import Transfer
from core.information_state import (
    InformationStatus,
    classify_information,
)
from core.partial_knowledge import PartialKnowledge


def test_complete_knowledge_is_complete():
    event = Transfer("alice", "bob", 3, 0)

    knowledge = PartialKnowledge(
        events=frozenset({event})
    )

    assert classify_information(
        knowledge
    ) == InformationStatus.COMPLETE


def test_missing_parent_is_incomplete():
    parent = Transfer("alice", "bob", 3, 0)

    child = Transfer(
        "bob",
        "carol",
        2,
        0,
        parents=(parent.event_id(),),
    )

    knowledge = PartialKnowledge(
        events=frozenset({child})
    )

    assert classify_information(
        knowledge
    ) == InformationStatus.INCOMPLETE


def test_known_conflict_is_ambiguous():
    first = Transfer("alice", "bob", 3, 0)
    second = Transfer("alice", "carol", 4, 0)

    knowledge = PartialKnowledge(
        events=frozenset({
            first,
            second,
        })
    )

    conflict = ConflictState(
        alternatives=(first, second)
    )

    assert classify_information(
        knowledge,
        conflict,
    ) == InformationStatus.AMBIGUOUS


def test_incomplete_knowledge_does_not_become_ambiguous_without_evidence():
    event = Transfer("alice", "bob", 3, 0)

    knowledge = PartialKnowledge(
        events=frozenset({event})
    )

    assert classify_information(
        knowledge
    ) == InformationStatus.COMPLETE
