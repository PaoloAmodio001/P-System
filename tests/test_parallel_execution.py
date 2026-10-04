from core.event import Transfer
from core.parallel_execution import ParallelExecution


def test_parallel_execution_contains_event_ids():
    events = (
        Transfer("alice", "bob", 10, 0),
        Transfer("carol", "dave", 20, 0),
    )

    parallel = ParallelExecution(events)

    assert parallel.event_ids == tuple(
        event.event_id()
        for event in events
    )


def test_parallel_execution_knows_events_are_independent():
    first = Transfer("alice", "bob", 10, 0)
    second = Transfer("carol", "dave", 20, 0)

    parallel = ParallelExecution((first, second))

    assert parallel.is_parallel(first, second)


def test_parallel_execution_rejects_self_pair():
    first = Transfer("alice", "bob", 10, 0)

    parallel = ParallelExecution((first,))

    assert not parallel.is_parallel(first, first)
def test_parallel_execution_does_not_materialize_pairs():
    events = tuple(
        Transfer(
            f"user_{i}",
            f"receiver_{i}",
            1,
            0,
        )
        for i in range(100)
    )

    parallel = ParallelExecution(events)

    assert len(parallel.event_ids) == 100
    assert not hasattr(parallel, "pairs")
