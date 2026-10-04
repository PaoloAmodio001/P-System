from core.event import Transfer
from core.signed_event import SignedTransfer
from crypto.identity import Identity


def test_signed_transfer_is_valid():

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

    assert signed.verify()


def test_modified_transfer_is_rejected():

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
        transfer=modified,
        public_key=signed.public_key,
        signature=signed.signature,
    )

    assert not forged.verify()


def test_modified_amount_is_rejected():

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
        "bob",
        5000,
        0,
    )

    forged = SignedTransfer(
        transfer=modified,
        public_key=signed.public_key,
        signature=signed.signature,
    )

    assert not forged.verify()
