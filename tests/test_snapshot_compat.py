from core.event import Transfer
from core.snapshot import GraphSnapshot
from core.snapshot_compat import compatible


def test_identical_snapshots_are_compatible():
    tx = Transfer(
        "alice",
        "bob",
        5,
        0,
    )

    snapshot_a = GraphSnapshot(
        events=(tx,),
        frontier=frozenset({tx.event_id()}),
    )

    snapshot_b = GraphSnapshot(
        events=(tx,),
        frontier=frozenset({tx.event_id()}),
    )

    assert compatible(snapshot_a, snapshot_b)


def test_independent_partial_snapshots_are_compatible():
    tx_a = Transfer(
        "alice",
        "bob",
        5,
        0,
    )

    tx_b = Transfer(
        "carol",
        "dave",
        3,
        0,
    )

    snapshot_a = GraphSnapshot(
        events=(tx_a,),
        frontier=frozenset({tx_a.event_id()}),
    )

    snapshot_b = GraphSnapshot(
        events=(tx_b,),
        frontier=frozenset({tx_b.event_id()}),
    )

    assert compatible(snapshot_a, snapshot_b)


def test_conflicting_snapshots_are_incompatible():
    tx_a = Transfer(
        "alice",
        "bob",
        8,
        0,
    )

    tx_b = Transfer(
        "alice",
        "carol",
        8,
        0,
    )

    snapshot_a = GraphSnapshot(
        events=(tx_a,),
        frontier=frozenset({tx_a.event_id()}),
    )

    snapshot_b = GraphSnapshot(
        events=(tx_b,),
        frontier=frozenset({tx_b.event_id()}),
    )

    assert not compatible(snapshot_a, snapshot_b)
