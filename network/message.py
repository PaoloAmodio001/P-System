from core.event import Transfer
from core.signed_event import SignedTransfer


def encode_signed_transfer(
    event: SignedTransfer,
) -> dict:
    return {
        "type": "SIGNED_TRANSFER",
        "transfer": {
            "sender": event.transfer.sender,
            "receiver": event.transfer.receiver,
            "amount": event.transfer.amount,
            "nonce": event.transfer.nonce,
            "parents": list(event.transfer.parents),
        },
        "public_key": event.public_key.hex(),
        "signature": event.signature.hex(),
    }


def decode_signed_transfer(
    message: dict,
) -> SignedTransfer:

    if message.get("type") != "SIGNED_TRANSFER":
        raise ValueError("INVALID MESSAGE TYPE")

    data = message["transfer"]

    transfer = Transfer(
        sender=data["sender"],
        receiver=data["receiver"],
        amount=data["amount"],
        nonce=data["nonce"],
        parents=tuple(data.get("parents", [])),
    )

    return SignedTransfer(
        transfer=transfer,
        public_key=bytes.fromhex(
            message["public_key"]
        ),
        signature=bytes.fromhex(
            message["signature"]
        ),
    )
