import re

from core.attestation import (
    EpochChange,
    EpochClosure,
    Snapshot,
    SnapshotAttestation,
    EpochReport,
    QuorumCertificate,
    Vote,
    is_well_formed_event,
)
from core.event import Transfer
from core.signed_event import SignedTransfer
from core.state import State


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


def _check_epoch(value) -> None:
    # The bound is what SQLite can compare, which no chain of committees will reach.
    if type(value) is not int or not 0 < value < 2**63:
        raise ValueError("INVALID QUORUM MESSAGE")


def encode_vote_request(event: SignedTransfer) -> dict:
    return {
        "type": "VOTE_REQUEST",
        "transfer": _encode_quorum_event(event.transfer),
        "public_key": event.public_key.hex(),
        "signature": event.signature.hex(),
    }


def _signed_event_of(data: dict) -> SignedTransfer:
    return SignedTransfer(
        transfer=_decode_quorum_event(data["transfer"]),
        public_key=_hex_bytes(data["public_key"], _PUBLIC_KEY_PATTERN),
        signature=_hex_bytes(data["signature"], _SIGNATURE_PATTERN),
    )


def decode_vote_request(message) -> SignedTransfer:
    return _signed_event_of(
        _message_of_type(
            message,
            "VOTE_REQUEST",
            "transfer",
            "public_key",
            "signature",
        )
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
    message = {
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

    # Only from epoch 1, so that each certificate has one form on the wire.
    if certificate.epoch != 0:
        message["epoch"] = certificate.epoch

    return message


def decode_certificate(message) -> QuorumCertificate:
    has_epoch = type(message) is dict and "epoch" in message
    fields = ("transfer", "votes", "epoch") if has_epoch else ("transfer", "votes")
    data = _message_of_type(message, "CERTIFICATE", *fields)

    if type(data["votes"]) is not list:
        raise ValueError("INVALID QUORUM MESSAGE")

    if has_epoch:
        _check_epoch(data["epoch"])

    votes = []

    for value in data["votes"]:
        entry = _object_with_fields(value, "validator", "signature")
        votes.append(
            _decode_vote_fields(entry["validator"], entry["signature"])
        )

    return QuorumCertificate(
        event=_decode_quorum_event(data["transfer"]),
        votes=tuple(votes),
        epoch=data["epoch"] if has_epoch else 0,
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


def encode_certificate_sync_request(frontier: dict[str, int], epoch: int = 0) -> dict:
    """
    For each sender, the next nonce the node asks for. A sender that is not listed
    is one the node knows nothing about. `epoch` is the one the node is in, left out
    when it is 0.
    """
    message = {
        "type": "CERTIFICATE_SYNC_REQUEST",
        "frontier": [
            [sender, frontier[sender]]
            for sender in sorted(frontier)
        ],
    }

    if epoch != 0:
        message["epoch"] = epoch

    return message


def certificate_sync_request_epoch(message) -> int:
    """The epoch in a request, which decode_certificate_sync_request has checked."""
    return message.get("epoch", 0)


def decode_certificate_sync_request(message) -> dict[str, int]:
    has_epoch = type(message) is dict and "epoch" in message
    fields = ("frontier", "epoch") if has_epoch else ("frontier",)
    data = _message_of_type(message, "CERTIFICATE_SYNC_REQUEST", *fields)

    if type(data["frontier"]) is not list:
        raise ValueError("INVALID QUORUM MESSAGE")

    if has_epoch:
        _check_epoch(data["epoch"])

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


# Epochs. The same rule as the decoders above: a well-formed value or ValueError.

_ID_PATTERN = re.compile(r"[0-9a-f]{64}")


def _encode_signed_event(event: SignedTransfer) -> dict:
    return {
        "transfer": _encode_quorum_event(event.transfer),
        "public_key": event.public_key.hex(),
        "signature": event.signature.hex(),
    }


def _decode_signed_event(value) -> SignedTransfer:
    return _signed_event_of(_object_with_fields(value, "transfer", "public_key", "signature"))


def _natural(value) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("INVALID QUORUM MESSAGE")

    return value


def _list_of(value) -> list:
    if type(value) is not list:
        raise ValueError("INVALID QUORUM MESSAGE")

    return value


def _encode_change(change: EpochChange) -> dict:
    return {
        "previous": change.previous_id,
        "members": [member.hex() for member in change.next_members],
        "f": change.next_f,
        "signatures": [
            [index, signature.hex()]
            for index, signature in change.signatures
        ],
    }


def _decode_change(value) -> EpochChange:
    data = _object_with_fields(value, "previous", "members", "f", "signatures")
    signatures = []

    for entry in _list_of(data["signatures"]):
        if not (type(entry) is list and len(entry) == 2):
            raise ValueError("INVALID QUORUM MESSAGE")

        signatures.append(
            (_natural(entry[0]), _hex_bytes(entry[1], _SIGNATURE_PATTERN))
        )

    return EpochChange(
        previous_id=_hex_bytes(data["previous"], _ID_PATTERN).hex(),
        next_members=tuple(
            _hex_bytes(member, _PUBLIC_KEY_PATTERN)
            for member in _list_of(data["members"])
        ),
        next_f=_natural(data["f"]),
        signatures=tuple(signatures),
    )


def encode_epoch_change(change: EpochChange) -> dict:
    return {"type": "EPOCH_CHANGE", "change": _encode_change(change)}


def decode_epoch_change(message) -> EpochChange:
    return _decode_change(_message_of_type(message, "EPOCH_CHANGE", "change")["change"])


def _encode_report(report: EpochReport) -> dict:
    return {
        "validator": report.validator,
        "votes": [_encode_signed_event(signed) for signed in report.votes],
        "signature": report.signature.hex(),
    }


def _decode_report(value) -> EpochReport:
    data = _object_with_fields(value, "validator", "votes", "signature")
    votes = tuple(_decode_signed_event(item) for item in _list_of(data["votes"]))
    return EpochReport(_natural(data["validator"]), votes, _hex_bytes(data["signature"], _SIGNATURE_PATTERN))


def encode_epoch_report(change_id: str, report: EpochReport) -> dict:
    return {
        "type": "EPOCH_REPORT",
        "change_id": change_id,
        "report": _encode_report(report),
    }


def decode_epoch_report(message) -> tuple[str, EpochReport]:
    data = _message_of_type(message, "EPOCH_REPORT", "change_id", "report")
    return (
        _hex_bytes(data["change_id"], _ID_PATTERN).hex(),
        _decode_report(data["report"]),
    )


def _encode_closure(closure: EpochClosure) -> dict:
    return {
        "change": _encode_change(closure.change),
        "reports": [_encode_report(report) for report in closure.reports],
    }


def _decode_closure(value) -> EpochClosure:
    data = _object_with_fields(value, "change", "reports")
    reports = tuple(_decode_report(item) for item in _list_of(data["reports"]))
    return EpochClosure(_decode_change(data["change"]), reports)


def encode_epoch_closure(closure: EpochClosure) -> dict:
    return {"type": "EPOCH_CLOSURE", "closure": _encode_closure(closure)}


def decode_epoch_closure(message) -> EpochClosure:
    return _decode_closure(_message_of_type(message, "EPOCH_CLOSURE", "closure")["closure"])


# Snapshots.


def _encode_attestation(attestation: SnapshotAttestation) -> dict:
    return {
        "validator": attestation.validator,
        "locks": [_encode_quorum_event(event) for event in attestation.locks],
        "signature": attestation.signature.hex(),
    }


def _decode_attestation(value) -> SnapshotAttestation:
    data = _object_with_fields(value, "validator", "locks", "signature")
    vote = _decode_vote_fields(data["validator"], data["signature"])
    return SnapshotAttestation(
        vote.validator,
        tuple(_decode_quorum_event(event) for event in _list_of(data["locks"])),
        vote.signature,
    )


def _decode_amounts(value) -> dict[str, int]:
    if type(value) is not dict or not all(type(key) is str for key in value):
        raise ValueError("INVALID QUORUM MESSAGE")

    return {key: _natural(amount) for key, amount in value.items()}


def encode_snapshot_request(epoch: int, digest: str, nonces: dict[str, int]) -> dict:
    """Only what a member needs to recompute it: the floor, and what it must come to."""
    return {
        "type": "SNAPSHOT_REQUEST",
        "epoch": epoch,
        "digest": digest,
        "nonces": dict(sorted(nonces.items())),
    }


def decode_snapshot_request(message) -> tuple[int, str, dict[str, int]]:
    data = _message_of_type(message, "SNAPSHOT_REQUEST", "epoch", "digest", "nonces")
    return (
        _natural(data["epoch"]),
        _hex_bytes(data["digest"], _ID_PATTERN).hex(),
        _decode_amounts(data["nonces"]),
    )


def encode_snapshot_vote(digest: str, attestation: SnapshotAttestation) -> dict:
    return {
        "type": "SNAPSHOT_VOTE",
        "digest": digest,
        "attestation": _encode_attestation(attestation),
    }


def decode_snapshot_vote(message) -> tuple[str, SnapshotAttestation]:
    data = _message_of_type(message, "SNAPSHOT_VOTE", "digest", "attestation")
    return _hex_bytes(data["digest"], _ID_PATTERN).hex(), _decode_attestation(data["attestation"])


def encode_snapshot(snapshot: Snapshot) -> dict:
    return {"type": "SNAPSHOT", "snapshot": encode_snapshot_body(snapshot)}


def encode_snapshot_body(snapshot: Snapshot) -> dict:
    return {
        "epoch": snapshot.epoch,
        "balances": dict(sorted(snapshot.state.balances.items())),
        "nonces": dict(sorted(snapshot.state.nonces.items())),
        "ids": list(snapshot.ids),
        "attestations": [_encode_attestation(item) for item in snapshot.attestations],
    }


def decode_snapshot_body(value) -> Snapshot:
    data = _object_with_fields(value, "epoch", "balances", "nonces", "ids", "attestations")
    ids = _list_of(data["ids"])

    for event_id in ids:
        _hex_bytes(event_id, _ID_PATTERN)

    return Snapshot(
        _natural(data["epoch"]),
        State(_decode_amounts(data["balances"]), _decode_amounts(data["nonces"])),
        tuple(ids),
        tuple(_decode_attestation(item) for item in _list_of(data["attestations"])),
    )


def decode_snapshot(message) -> Snapshot:
    return decode_snapshot_body(_message_of_type(message, "SNAPSHOT", "snapshot")["snapshot"])
