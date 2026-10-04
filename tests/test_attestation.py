from core.attestation import Attestation
from core.event import Transfer
from crypto.identity import Identity


def test_attestation_is_cryptographically_verifiable():
    identity = Identity.create()

    tx = Transfer(
        sender="alice",
        receiver="bob",
        amount=8,
        nonce=0,
    )

    attestation = Attestation.create(
        identity=identity,
        event_id=tx.event_id(),
        sequence=1,
    )

    assert attestation.verify()


def test_attestation_tampering_is_rejected():
    identity = Identity.create()

    tx = Transfer(
        sender="alice",
        receiver="bob",
        amount=8,
        nonce=0,
    )

    attestation = Attestation.create(
        identity=identity,
        event_id=tx.event_id(),
        sequence=1,
    )

    tampered = Attestation(
        event_id=attestation.event_id,
        observer=attestation.observer,
        sequence=2,
        signature=attestation.signature,
    )

    assert not tampered.verify()
