"""
Mission records: structured data that P-System certifies (docs/MISSION-RECORDS.md).

A mission record is an ordinary event of the protocol whose `data` is the canonical text of a record.
Nothing in the protocol changes:

- The event moves one unit of a *record asset* that the producing node issues itself
  (`<node>.records.<supply>`), from the node's account of that asset to an account named after the
  entity the record is about. Moving one unit makes it an executable transfer of the model
  (`Executable` needs a positive amount), so every theorem about events holds for records as is.
  The balance of an entity account counts the records it received; the fixed supply bounds how many
  records a node can ever produce (`RECORD_SUPPLY`).
- The data is part of the canonical form, so of the event id and of the signature. Two versions of a
  record for one `(sender, nonce)` are two events with different ids: the committee decides one, as
  for any spend, and a node that signed both has equivocated (`EquivocationProof`).
- The record carries its own provenance: who produced it (`origin`, the account that signs it),
  about which entity, which logical version of that entity, and the SHA-256 of its body.

This module only builds and reads records. Signing, sending and proving go through `Wallet`,
`Client` and `ChainVerifier` as for any event.
"""

from dataclasses import dataclass
from hashlib import sha256
import json

from core.event import MAX_DATA_BYTES, Transfer, canonical_data
from core.state import asset_account, asset_id, split_asset_account
from network.message import decode_certificate

RECORD_SCHEMA = "psystem-mission-record/1"
RECORD_ASSET_NAME = "records"
# How many records one node can produce: the supply of its record asset.
RECORD_SUPPLY = 10**15
RECORD_KINDS = ("telemetry", "observation", "plan", "result", "status", "command", "report")
_ENTITY_MAX = 256


class RecordError(ValueError):
    """Not a mission record, or not one this module can build."""


def record_asset(identity_id: str) -> str:
    """The record asset a node with this identity issues."""
    return asset_id(identity_id, RECORD_ASSET_NAME, RECORD_SUPPLY)


def entity_account(entity: str, asset: str) -> str:
    """The account of `asset` that receives the records about `entity`."""
    return asset_account(sha256(b"P-SYSTEM/ENTITY\0" + entity.encode()).hexdigest(), asset)


def body_digest(body: dict) -> str:
    return sha256(canonical_data(body).encode()).hexdigest()


@dataclass(frozen=True)
class MissionRecord:
    entity: str
    kind: str
    version: int
    body: dict
    origin: str
    produced_utc: str
    schema: str = RECORD_SCHEMA

    def to_data(self) -> str:
        if type(self.entity) is not str or not 0 < len(self.entity) <= _ENTITY_MAX:
            raise RecordError(f"ENTITY IS A STRING OF 1 TO {_ENTITY_MAX} CHARACTERS")
        if self.kind not in RECORD_KINDS:
            raise RecordError(f"KIND IS ONE OF {RECORD_KINDS}")
        if type(self.version) is not int or self.version < 0:
            raise RecordError("VERSION IS A NATURAL NUMBER")
        if type(self.origin) is not str or not self.origin:
            raise RecordError("ORIGIN IS REQUIRED")
        if type(self.produced_utc) is not str or not self.produced_utc:
            raise RecordError("PRODUCED_UTC IS REQUIRED")
        try:
            return canonical_data(
                {
                    "schema": self.schema,
                    "entity": self.entity,
                    "kind": self.kind,
                    "version": self.version,
                    "origin": self.origin,
                    "produced_utc": self.produced_utc,
                    "body_sha256": body_digest(self.body),
                    "body": self.body,
                }
            )
        except ValueError as error:
            raise RecordError(str(error)) from error

    @classmethod
    def from_data(cls, data: str) -> "MissionRecord":
        try:
            value = json.loads(data)
        except ValueError as error:
            raise RecordError("DATA IS NOT JSON") from error
        if type(value) is not dict or value.get("schema") != RECORD_SCHEMA:
            raise RecordError("NOT A MISSION RECORD")
        expected = {"schema", "entity", "kind", "version", "origin", "produced_utc", "body_sha256", "body"}
        if set(value) != expected:
            raise RecordError("FIELDS OF A MISSION RECORD")
        record = cls(
            entity=value["entity"],
            kind=value["kind"],
            version=value["version"],
            body=value["body"],
            origin=value["origin"],
            produced_utc=value["produced_utc"],
        )
        if type(record.body) is not dict or body_digest(record.body) != value["body_sha256"]:
            raise RecordError("BODY DOES NOT MATCH ITS DIGEST")
        if record.to_data() != data:
            raise RecordError("DATA IS NOT THE CANONICAL TEXT OF ITS RECORD")
        return record


def record_receiver(wallet, entity: str) -> str:
    """The receiver of a record about `entity` from this wallet (a wallet of the record asset)."""
    if wallet.asset is None:
        raise RecordError("THE WALLET HOLDS NO RECORD ASSET")
    return entity_account(entity, wallet.asset)


def sign_record(wallet, record: MissionRecord, nonce: int | None = None, parents=()):
    """Sign a record with a wallet of its record asset. The journal of the wallet holds it first."""
    if wallet.asset != record_asset(wallet.identity.identity_id):
        raise RecordError("THE WALLET IS NOT ON THE RECORD ASSET OF ITS IDENTITY")
    if record.origin != wallet.account:
        raise RecordError("ORIGIN IS THE ACCOUNT THAT SIGNS")
    return wallet.transfer(record_receiver(wallet, record.entity), 1, nonce=nonce, parents=parents, data=record.to_data())


def is_record_event(event: Transfer) -> bool:
    """Whether an event has the shape of a mission record: one unit of a record asset, with data."""
    if event.data == "" or event.amount != 1:
        return False
    parts = split_asset_account(event.sender)
    if parts is None:
        return False
    owner, asset = parts
    if asset != record_asset(owner):
        return False
    try:
        record = MissionRecord.from_data(event.data)
    except RecordError:
        return False
    return record.origin == event.sender and event.receiver == entity_account(record.entity, asset)


@dataclass(frozen=True)
class CertifiedRecord:
    """A record with the certificate that decided it."""

    event_id: str
    sender: str
    nonce: int
    record: MissionRecord
    certificate: object

    def provenance(self) -> dict:
        certificate = self.certificate
        return {
            "event_id": self.event_id,
            "sender": self.sender,
            "nonce": self.nonce,
            "origin": self.record.origin,
            "entity": self.record.entity,
            "version": self.record.version,
            "body_sha256": body_digest(self.record.body),
            "parents": sorted(certificate.event.parents),
            "certificate_phase": certificate.phase,
            "certificate_round": certificate.round,
            "certificate_votes": len(certificate.votes),
            "committee_epoch": certificate.epoch,
        }


def certified_record(encoded_certificate: dict, verifier=None) -> CertifiedRecord:
    """
    Decode a certificate from the API into a certified record. With a `ChainVerifier`, the
    certificate is checked against the committee chain first; without one nothing is proved.
    """
    certificate = decode_certificate(encoded_certificate)
    if verifier is not None and not verifier.verify(certificate):
        raise RecordError("THE CERTIFICATE DOES NOT VERIFY")
    event = certificate.event
    if not is_record_event(event):
        raise RecordError("THE EVENT IS NOT A MISSION RECORD")
    return CertifiedRecord(
        event_id=event.event_id(),
        sender=event.sender,
        nonce=event.nonce,
        record=MissionRecord.from_data(event.data),
        certificate=certificate,
    )


__all__ = [
    "MAX_DATA_BYTES",
    "RECORD_SCHEMA",
    "RECORD_SUPPLY",
    "RECORD_KINDS",
    "MissionRecord",
    "CertifiedRecord",
    "RecordError",
    "record_asset",
    "entity_account",
    "record_receiver",
    "sign_record",
    "is_record_event",
    "certified_record",
]
