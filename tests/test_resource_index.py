from core.event import Transfer
from core.resource_index import ResourceIndex


def test_resource_index_adds_events_and_counts_resources():
    events = [
        Transfer("alice", "bob", 10, 0),
        Transfer("carol", "dave", 20, 0),
        Transfer("eve", "frank", 3, 0),
    ]

    index = ResourceIndex()
    index.add_all(events)

    assert len(index) == 3
    assert index.resource_count == 9


def test_resource_index_finds_overlapping_events():
    first = Transfer("alice", "bob", 10, 0)
    second = Transfer("carol", "dave", 20, 0)
    overlapping = Transfer("alice", "carol", 5, 1)

    index = ResourceIndex()
    index.add_all([first, second, overlapping])

    assert index.overlapping_event_ids(first) == frozenset({
        overlapping.event_id(),
    })

    assert index.overlapping_event_ids(second) == frozenset({
        overlapping.event_id(),
    })

    assert index.overlapping_event_ids(overlapping) == frozenset({
        first.event_id(),
        second.event_id(),
    })


def test_resource_index_returns_empty_for_disjoint_event():
    first = Transfer("alice", "bob", 10, 0)
    second = Transfer("carol", "dave", 20, 0)

    index = ResourceIndex()
    index.add_all([first, second])

    assert index.overlapping_event_ids(first) == frozenset()
    assert index.overlapping_event_ids(second) == frozenset()


def test_resource_index_does_not_duplicate_events():
    event = Transfer("alice", "bob", 10, 0)

    index = ResourceIndex()
    index.add(event)
    index.add(event)

    assert len(index) == 1
    assert index.resource_count == 3
