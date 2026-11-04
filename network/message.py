import re

from core.attestation import (
    QuorumCertificate,
    Vote,
    is_well_formed_event,
)
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


# Quorum mode: docs/FORMAL-SPECIFICATION.md, section 13.1.
#
# A decoder takes what any peer sent. It returns a well-formed value or raises
# ValueError, and never anything else. It does not check signatures or the rules
# of a certificate: QuorumCertificate.verify does that, and an invalid certificate
# of the right form decodes normally.

_PUBLIC_KEY_PATTERN = re.compile(r"[0-9a-f]{64}")
_SIGNATURE_PATTERN = re.compile(r"[0-9a-f]{128}")


def _object_with_fields(value, *fields: str) -> dict:
    if type(value) is not dict or value.keys() != set(fields):
        raise ValueError("INVALID QUORUM MESSAGE")

    return value


def _message_of_type(value, message_type: str, *fields: str) -> dict:
    message = _object_with_fields(value, "type", *fields)

    if message["type"] != message_type:
        raise ValueError("INVALID QUORUM MESSAGE")

    return message


def _hex_bytes(value, pattern: re.Pattern) -> bytes:
    # Checked here because bytes.fromhex also takes uppercase and spaces, and each
    # value must have one form on the wire.
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise ValueError("INVALID QUORUM MESSAGE")

    return bytes.fromhex(value)


def _encode_quorum_event(event: Transfer) -> dict:
    return {
        "sender": event.sender,
        "receiver": event.receiver,
        "amount": event.amount,
        "nonce": event.nonce,
        "parents": sorted(event.parents),
    }


def _decode_quorum_event(value) -> Transfer:
    data = _object_with_fields(
        value,
        "sender",
        "receiver",
        "amount",
        "nonce",
        "parents",
    )

    if type(data["parents"]) is not list:
        raise ValueError("INVALID QUORUM MESSAGE")

    event = Transfer(
        sender=data["sender"],
        receiver=data["receiver"],
        amount=data["amount"],
        nonce=data["nonce"],
        parents=tuple(data["parents"]),
    )

    if not is_well_formed_event(event):
        raise ValueError("MALFORMED EVENT")

    # Sorted as in canonical(), so that one event is one value under ==. Signatures
    # are on the canonical form and stay valid.
    return Transfer(
        sender=event.sender,
        receiver=event.receiver,
        amount=event.amount,
        nonce=event.nonce,
        parents=tuple(sorted(event.parents)),
    )


def _decode_vote_fields(validator, signature) -> Vote:
    # An index beyond the committee has the right form: verify refuses it.
    if type(validator) is not int or validator < 0:
        raise ValueError("INVALID QUORUM MESSAGE")

    return Vote(
        validator=validator,
        signature=_hex_bytes(signature, _SIGNATURE_PATTERN),
    )


def encode_vote_request(event: SignedTransfer) -> dict:
    return {
        "type": "VOTE_REQUEST",
        "transfer": _encode_quorum_event(event.transfer),
        "public_key": event.public_key.hex(),
        "signature": event.signature.hex(),
    }


def decode_vote_request(message) -> SignedTransfer:
    data = _message_of_type(
        message,
        "VOTE_REQUEST",
        "transfer",
        "public_key",
        "signature",
    )

    return SignedTransfer(
        transfer=_decode_quorum_event(data["transfer"]),
        public_key=_hex_bytes(data["public_key"], _PUBLIC_KEY_PATTERN),
        signature=_hex_bytes(data["signature"], _SIGNATURE_PATTERN),
    )


def encode_vote(event: Transfer, vote: Vote) -> dict:
    return {
        "type": "VOTE",
        "transfer": _encode_quorum_event(event),
        "validator": vote.validator,
        "signature": vote.signature.hex(),
    }


def decode_vote(message) -> tuple[Transfer, Vote]:
    data = _message_of_type(
        message,
        "VOTE",
        "transfer",
        "validator",
        "signature",
    )

    return (
        _decode_quorum_event(data["transfer"]),
        _decode_vote_fields(data["validator"], data["signature"]),
    )


def encode_certificate(certificate: QuorumCertificate) -> dict:
    return {
        "type": "CERTIFICATE",
        "transfer": _encode_quorum_event(certificate.event),
        "votes": [
            {
                "validator": vote.validator,
                "signature": vote.signature.hex(),
            }
            for vote in certificate.votes
        ],
    }


def decode_certificate(message) -> QuorumCertificate:
    data = _message_of_type(message, "CERTIFICATE", "transfer", "votes")

    if type(data["votes"]) is not list:
        raise ValueError("INVALID QUORUM MESSAGE")

    votes = []

    for value in data["votes"]:
        entry = _object_with_fields(value, "validator", "signature")
        votes.append(
            _decode_vote_fields(entry["validator"], entry["signature"])
        )

    return QuorumCertificate(
        event=_decode_quorum_event(data["transfer"]),
        votes=tuple(votes),
    )


def encode_certificate_sync(certificates) -> dict:
    """The certificates in the given order, which is the order of the log."""
    return {
        "type": "CERTIFICATE_SYNC",
        "certificates": [
            encode_certificate(certificate)
            for certificate in certificates
        ],
    }


def decode_certificate_sync(message) -> list[QuorumCertificate]:
    data = _message_of_type(message, "CERTIFICATE_SYNC", "certificates")

    if type(data["certificates"]) is not list:
        raise ValueError("INVALID QUORUM MESSAGE")

    return [decode_certificate(item) for item in data["certificates"]]


def encode_certificate_sync_request(frontier: dict[str, int]) -> dict:
    """
    For each sender, the next nonce the node asks for. A sender that is not listed
    is one the node knows nothing about.
    """
    return {
        "type": "CERTIFICATE_SYNC_REQUEST",
        "frontier": [
            [sender, frontier[sender]]
            for sender in sorted(frontier)
        ],
    }


def decode_certificate_sync_request(message) -> dict[str, int]:
    data = _message_of_type(message, "CERTIFICATE_SYNC_REQUEST", "frontier")

    if type(data["frontier"]) is not list:
        raise ValueError("INVALID QUORUM MESSAGE")

    frontier = {}
    previous = None

    for entry in data["frontier"]:
        if type(entry) is not list or len(entry) != 2:
            raise ValueError("INVALID QUORUM MESSAGE")

        sender, nonce = entry

        # The rules of an event, so that a frontier holds nothing an event could not.
        if not is_well_formed_event(Transfer(sender, sender, 0, nonce)):
            raise ValueError("INVALID QUORUM MESSAGE")

        # Strictly increasing, so that each frontier has one form on the wire.
        if previous is not None and sender <= previous:
            raise ValueError("INVALID QUORUM MESSAGE")

        frontier[sender] = nonce
        previous = sender

    return frontier
