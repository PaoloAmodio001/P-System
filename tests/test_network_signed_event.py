from core.event import Transfer
from core.signed_event import SignedTransfer
from crypto.identity import Identity
from network.message import (
    decode_signed_transfer,
    encode_signed_transfer,
)


def test_signed_transfer_survives_network_serialization():
    identity = Identity.create()

    transfer = Transfer(
        sender="alice",
        receiver="bob",
        amount=3,
        nonce=0,
    )

    signed = SignedTransfer.create(
        identity,
        transfer,
    )

    message = encode_signed_transfer(
        signed
    )

    restored = decode_signed_transfer(
        message
    )

    assert restored.transfer == transfer
    assert restored.public_key == signed.public_key
    assert restored.signature == signed.signature
    assert restored.verify()


def test_tampered_transfer_fails_signature():
    identity = Identity.create()

    transfer = Transfer(
        sender="alice",
        receiver="bob",
        amount=3,
        nonce=0,
    )

    signed = SignedTransfer.create(
        identity,
        transfer,
    )

    message = encode_signed_transfer(
        signed
    )

    message["transfer"]["amount"] = 9

    restored = decode_signed_transfer(
        message
    )

    assert not restored.verify()
