from core.event import Transfer
from core.snapshot import GraphSnapshot


def test_complete_graph_snapshot():
    tx_a = Transfer(
        "alice",
        "bob",
        4,
        0,
    )

    tx_b = Transfer(
        "alice",
        "carol",
        3,
        1,
        parents=(tx_a.event_id(),),
    )

    snapshot = GraphSnapshot(
        events=(tx_a, tx_b),
        frontier=frozenset({
            tx_b.event_id(),
        }),
    )

    assert snapshot.complete()
    assert snapshot.missing_parents() == frozenset()

    assert snapshot.contains(tx_a.event_id())
    assert snapshot.contains(tx_b.event_id())


def test_partial_graph_snapshot_detects_missing_parent():
    tx_a = Transfer(
        "alice",
        "bob",
        4,
        0,
    )

    tx_b = Transfer(
        "alice",
        "carol",
        3,
        1,
        parents=(tx_a.event_id(),),
    )

    snapshot = GraphSnapshot(
        events=(tx_b,),
        frontier=frozenset({
            tx_b.event_id(),
        }),
    )

    assert not snapshot.complete()
    assert snapshot.missing_parents() == frozenset({
        tx_a.event_id(),
    })

    assert not snapshot.contains(tx_a.event_id())
    assert snapshot.contains(tx_b.event_id())
