from core.event import Transfer
from core.execution_index import ExecutionIndex


def test_execution_index_adds_events():
    events = [
        Transfer("alice", "bob", 10, 0),
        Transfer("carol", "dave", 20, 0),
        Transfer("eve", "frank", 3, 0),
    ]

    index = ExecutionIndex()
    index.add_all(events)

    assert len(index) == 3
    assert index.resource_count == 9


def test_execution_index_finds_overlaps():
    first = Transfer("alice", "bob", 10, 0)
    second = Transfer("carol", "dave", 20, 0)
    overlapping = Transfer("alice", "carol", 5, 1)

    index = ExecutionIndex()
    index.add_all([first, second, overlapping])

    assert {
        event.event_id()
        for event in index.overlaps(first)
    } == {
        overlapping.event_id()
    }

    assert {
        event.event_id()
        for event in index.overlaps(second)
    } == {
        overlapping.event_id()
    }

    assert {
        event.event_id()
        for event in index.overlaps(overlapping)
    } == {
        first.event_id(),
        second.event_id(),
    }


def test_execution_index_identifies_independent_event():
    first = Transfer("alice", "bob", 10, 0)
    second = Transfer("carol", "dave", 20, 0)

    index = ExecutionIndex()
    index.add(first)

    assert index.independent(first)
    assert index.independent(second)

    index.add(second)

    assert index.independent(first)
    assert index.independent(second)


def test_execution_index_detects_interaction():
    first = Transfer("alice", "bob", 10, 0)
    second = Transfer("alice", "carol", 5, 1)

    index = ExecutionIndex()
    index.add_all([first, second])

    assert not index.independent(first)
    assert not index.independent(second)
