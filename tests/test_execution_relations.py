from core.event import Transfer
from core.execution_relations import build_execution_relations


def test_build_execution_relations():
    first = Transfer("alice", "bob", 3, 0)

    second = Transfer(
        "bob",
        "carol",
        2,
        0,
        parents=(first.event_id(),),
    )

    independent = Transfer("carol", "dave", 1, 0)

    conflict = Transfer("alice", "carol", 4, 0)

    relations = build_execution_relations([
        first,
        second,
        independent,
        conflict,
    ])

    assert (first.event_id(), second.event_id()) in relations.causal
    assert (first.event_id(), independent.event_id()) in relations.parallel
    assert (first.event_id(), conflict.event_id()) in relations.conflicts
    assert relations.has_conflicts()
