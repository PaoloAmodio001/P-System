from core.event import Transfer
from core.signed_event import SignedTransfer
from core.evidence import Evidence
from crypto.identity import Identity


def test_valid_evidence():

    identity = Identity.create()

    tx = Transfer(
        "alice",
        "bob",
        5,
        0,
    )

    signed = SignedTransfer.create(
        identity,
        tx,
    )

    evidence = Evidence(
        event=signed,
        observed_by=frozenset({
            "node-1",
            "node-2",
            "node-3",
        }),
    )

    assert evidence.valid()
    assert evidence.strength() == 3


def test_invalid_event_is_invalid_evidence():

    identity = Identity.create()

    tx = Transfer(
        "alice",
        "bob",
        5,
        0,
    )

    signed = SignedTransfer.create(
        identity,
        tx,
    )

    modified = Transfer(
        "alice",
        "attacker",
        500,
        0,
    )

    forged = SignedTransfer(
        modified,
        signed.public_key,
        signed.signature,
    )

    evidence = Evidence(
        event=forged,
        observed_by=frozenset({
            "node-1",
            "node-2",
            "node-3",
            "node-4",
        }),
    )

    assert not evidence.valid()
