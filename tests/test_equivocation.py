from core.event import Transfer
from core.equivocation import EquivocationProof
from core.signed_event import SignedTransfer
from crypto.identity import Identity


def test_valid_equivocation_is_detected():
    identity = Identity.create()

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

    signed_a = SignedTransfer.create(identity, tx_a)
    signed_b = SignedTransfer.create(identity, tx_b)

    proof = EquivocationProof(
        first=signed_a,
        second=signed_b,
    )

    assert proof.verify()


def test_different_identities_are_not_equivocation():
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

    proof = EquivocationProof(
        first=signed_a,
        second=signed_b,
    )

    assert not proof.verify()


def test_different_nonces_are_not_equivocation():
    identity = Identity.create()

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
        nonce=1,
    )

    signed_a = SignedTransfer.create(identity, tx_a)
    signed_b = SignedTransfer.create(identity, tx_b)

    proof = EquivocationProof(
        first=signed_a,
        second=signed_b,
    )

    assert not proof.verify()


def test_same_transaction_is_not_equivocation():
    identity = Identity.create()

    tx = Transfer(
        sender="alice",
        receiver="bob",
        amount=8,
        nonce=0,
    )

    signed_a = SignedTransfer.create(identity, tx)
    signed_b = SignedTransfer.create(identity, tx)

    proof = EquivocationProof(
        first=signed_a,
        second=signed_b,
    )

    assert not proof.verify()


def test_tampered_signature_is_rejected():
    identity = Identity.create()

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

    signed_a = SignedTransfer.create(identity, tx_a)
    signed_b = SignedTransfer.create(identity, tx_b)

    tampered = SignedTransfer(
        transfer=Transfer(
            sender="alice",
            receiver="carol",
            amount=9,
            nonce=0,
        ),
        public_key=signed_b.public_key,
        signature=signed_b.signature,
    )

    proof = EquivocationProof(
        first=signed_a,
        second=tampered,
    )

    assert not proof.verify()
