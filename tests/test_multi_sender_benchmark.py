"""Small deterministic checks for the multi-sender benchmark workload."""

from benchmarks.quorum_benchmark import workload_events
from crypto.identity import Identity


def test_workload_round_robins_independent_nonce_streams():
    people = [Identity.create() for _ in range(3)]
    events = workload_events(people, 8)

    assert [event.transfer.sender for event in events] == [
        people[index % 3].identity_id for index in range(8)
    ]
    assert [event.transfer.nonce for event in events] == [0, 0, 0, 1, 1, 1, 2, 2]
    assert len({event.transfer.event_id() for event in events}) == 8


def test_workload_is_reproducible_for_the_same_identities_and_count():
    people = [Identity.create() for _ in range(2)]
    first = workload_events(people, 7)
    second = workload_events(people, 7)

    assert [event.transfer.canonical() for event in first] == [
        event.transfer.canonical() for event in second
    ]


def test_workload_rejects_unbounded_or_empty_requests():
    people = [Identity.create()]

    try:
        workload_events([], 1)
    except ValueError as error:
        assert "sender" in str(error)
    else:
        raise AssertionError("empty sender set was accepted")

    try:
        workload_events(people, 0)
    except ValueError as error:
        assert "count" in str(error)
    else:
        raise AssertionError("empty workload was accepted")
