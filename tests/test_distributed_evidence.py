from core.event import Transfer
from core.signed_event import SignedTransfer
from core.evidence import Evidence
from core.snapshot import GraphSnapshot
from crypto.identity import Identity


def test_distributed_evidence_can_be_different_for_conflicting_snapshots():
    identity_a = Identity.create()
    identity_b = Identity.create()

    tx_a = Transfer(
        sender="alice",
        receiver="bob",
        amount=8,
        nonce=0,
    )

    tx_b = Transfer(
        sender="alice",
        receiver="carol",
        amount=8,
        nonce=0,
    )

    signed_a = SignedTransfer.create(identity_a, tx_a)
    signed_b = SignedTransfer.create(identity_b, tx_b)

    evidence_a = Evidence(
        event=signed_a,
        observed_by=frozenset({
            "node-1",
            "node-2",
            "node-3",
        }),
    )

    evidence_b = Evidence(
        event=signed_b,
        observed_by=frozenset({
            "node-4",
            "node-5",
            "node-6",
        }),
    )

    snapshot_a = GraphSnapshot(
        events=(tx_a,),
        frontier=frozenset({tx_a.event_id()}),
    )

    snapshot_b = GraphSnapshot(
        events=(tx_b,),
        frontier=frozenset({tx_b.event_id()}),
    )

    assert evidence_a.valid()
    assert evidence_b.valid()

    assert snapshot_a.complete()
    assert snapshot_b.complete()

    assert evidence_a.strength() == 3
    assert evidence_b.strength() == 3

    assert tx_a.event_id() != tx_b.event_id()
