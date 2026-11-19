"""Events with data, and mission records on top of them (docs/MISSION-RECORDS.md)."""

import json
from hashlib import sha256

import pytest

from core.attestation import is_authorized_transfer, is_well_formed_event
from core.equivocation import EquivocationProof
from core.event import MAX_DATA_BYTES, Transfer, canonical_data, is_canonical_data
from core.resolver import ConflictResolver
from core.signed_event import SignedTransfer
from crypto.identity import Identity
from network.message import (
    decode_certificate,
    decode_vote_request,
    encode_certificate,
    encode_vote_request,
)
from network.quorum.store import _event_from_canonical
from sdk.client import Wallet, WalletError
from sdk.mission import (
    MissionRecord,
    RecordError,
    certified_record,
    entity_account,
    is_record_event,
    record_asset,
    sign_record,
)


def legacy_canonical(sender, receiver, amount, nonce, parents=()):
    """The canonical form as it was before data existed."""
    return json.dumps(
        {"sender": sender, "receiver": receiver, "amount": amount, "nonce": nonce, "parents": sorted(parents)},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


@pytest.fixture
def wallet(tmp_path):
    identity = Identity.create()
    made = Wallet(identity, tmp_path / "records.sqlite", asset=record_asset(identity.identity_id))
    yield made
    made.close()


def record(wallet, version=1, body=None, entity="rover-1"):
    return MissionRecord(
        entity=entity,
        kind="telemetry",
        version=version,
        body={"soc": 0.8, "pos_rc": [10, 20]} if body is None else body,
        origin=wallet.account,
        produced_utc="2026-11-15T12:00:00Z",
    )


# The event without data is the event it was: same canonical form, same id, same signatures.


@pytest.mark.parametrize("parents", [(), ("a" * 64,), ("b" * 64, "a" * 64)])
def test_an_event_without_data_keeps_its_canonical_form_and_id(parents):
    event = Transfer("alice", "bob", 7, 3, parents)
    old = legacy_canonical("alice", "bob", 7, 3, parents)
    assert event.canonical() == old
    assert event.event_id() == sha256(old).hexdigest()


def test_data_is_in_the_canonical_form_and_so_in_the_id():
    data = canonical_data({"x": 1})
    plain = Transfer("alice", "bob", 1, 0)
    carrying = Transfer("alice", "bob", 1, 0, (), data)
    assert json.loads(carrying.canonical())["data"] == data
    assert carrying.event_id() != plain.event_id()
    assert Transfer("alice", "bob", 1, 0, (), canonical_data({"x": 2})).event_id() != carrying.event_id()


def test_a_signature_covers_the_data():
    identity = Identity.create()
    event = Transfer(identity.identity_id, "bob", 1, 0, (), canonical_data({"x": 1}))
    signed = SignedTransfer.create(identity, event)
    assert signed.verify()
    tampered = SignedTransfer(
        Transfer(identity.identity_id, "bob", 1, 0, (), canonical_data({"x": 2})),
        signed.public_key,
        signed.signature,
    )
    assert not tampered.verify()


# One value of data has one text.


@pytest.mark.parametrize(
    "data",
    [
        '{"b":1,"a":2}',  # keys not sorted
        '{"a": 1}',  # spaces
        '[1,2]',  # not an object
        '"text"',
        "not json",
        '{"a":NaN}',
        '{"a":"è"}',  # not ASCII-escaped
        None,
        1,
    ],
)
def test_data_that_is_not_canonical_makes_an_event_malformed(data):
    assert not is_canonical_data(data)
    assert not is_well_formed_event(Transfer("alice", "bob", 1, 0, (), data))


def test_data_over_the_bound_is_refused():
    with pytest.raises(ValueError):
        canonical_data({"x": "y" * MAX_DATA_BYTES})
    assert not is_canonical_data('{"x":"' + "y" * MAX_DATA_BYTES + '"}')


def test_empty_data_is_well_formed_and_canonical_data_too():
    assert is_well_formed_event(Transfer("alice", "bob", 1, 0))
    assert is_well_formed_event(Transfer("alice", "bob", 1, 0, (), canonical_data({"è": [1, 2.5, None]})))


# The wire, the store and the wallet keep the data.


def test_a_vote_request_carries_the_data_and_only_when_there_is_some(wallet):
    signed = sign_record(wallet, record(wallet))
    message = json.loads(json.dumps(encode_vote_request(signed)))
    assert message["transfer"]["data"] == signed.transfer.data
    assert decode_vote_request(message) == signed

    plain = SignedTransfer.create(wallet.identity, Transfer(wallet.account, "x", 1, 0))
    assert "data" not in encode_vote_request(plain)["transfer"]


def test_an_empty_data_field_on_the_wire_is_refused(wallet):
    plain = SignedTransfer.create(wallet.identity, Transfer(wallet.account, "x", 1, 0))
    message = encode_vote_request(plain)
    message["transfer"]["data"] = ""
    with pytest.raises(ValueError):
        decode_vote_request(message)


def test_non_canonical_data_on_the_wire_is_refused(wallet):
    signed = sign_record(wallet, record(wallet))
    message = encode_vote_request(signed)
    message["transfer"]["data"] = json.dumps(json.loads(signed.transfer.data), indent=1)
    with pytest.raises(ValueError):
        decode_vote_request(message)


def test_the_store_decodes_the_data_it_wrote(wallet):
    event = sign_record(wallet, record(wallet)).transfer
    assert _event_from_canonical(event.canonical().decode()) == event


def test_a_certificate_carries_the_record(wallet):
    from core.attestation import QuorumCertificate

    event = sign_record(wallet, record(wallet)).transfer
    certificate = QuorumCertificate(event, ())
    assert decode_certificate(json.loads(json.dumps(encode_certificate(certificate)))).event == event


def test_the_wallet_replays_records_after_a_restart(tmp_path):
    identity = Identity.create()
    path = tmp_path / "w.sqlite"
    first = Wallet(identity, path, asset=record_asset(identity.identity_id))
    signed = [sign_record(first, record(first, version=v)) for v in (1, 2, 3)]
    first.close()
    again = Wallet(identity, path, asset=record_asset(identity.identity_id))
    assert again.unfinished(0) == signed
    # The same nonce for another record is refused, and nothing is signed.
    with pytest.raises(WalletError):
        sign_record(again, record(again, version=99), nonce=0)
    again.close()


def test_the_wallet_refuses_data_that_is_not_canonical(wallet):
    with pytest.raises(WalletError):
        wallet.transfer(entity_account("e", wallet.asset), 1, data='{"b":1,"a":2}')


# Records.


def test_a_record_is_an_authorized_executable_spend_of_its_asset(wallet):
    signed = sign_record(wallet, record(wallet))
    event = signed.transfer
    assert is_well_formed_event(event)
    assert is_authorized_transfer(signed)
    assert event.amount == 1 and event.sender != event.receiver
    assert event.receiver == entity_account("rover-1", wallet.asset)
    assert is_record_event(event)


def test_a_record_round_trips_and_its_body_is_bound_to_its_digest(wallet):
    original = record(wallet)
    data = original.to_data()
    assert MissionRecord.from_data(data) == original
    value = json.loads(data)
    value["body"]["soc"] = 0.1
    with pytest.raises(RecordError):
        MissionRecord.from_data(canonical_data(value))


def test_a_record_needs_its_fields(wallet):
    with pytest.raises(RecordError):
        MissionRecord("", "telemetry", 1, {}, wallet.account, "t").to_data()
    with pytest.raises(RecordError):
        MissionRecord("e", "gossip", 1, {}, wallet.account, "t").to_data()
    with pytest.raises(RecordError):
        MissionRecord("e", "plan", -1, {}, wallet.account, "t").to_data()


def test_a_record_signed_for_another_origin_is_refused(wallet):
    with pytest.raises(RecordError):
        sign_record(wallet, MissionRecord("e", "plan", 1, {}, "someone-else", "t"))


def test_an_event_that_lies_about_its_entity_is_not_a_record(wallet):
    event = sign_record(wallet, record(wallet)).transfer
    moved = Transfer(event.sender, entity_account("another", wallet.asset), 1, event.nonce, (), event.data)
    assert not is_record_event(moved)


def test_two_versions_of_one_record_slot_are_a_provable_conflict(wallet):
    first = sign_record(wallet, record(wallet, version=1, body={"soc": 0.8}), nonce=0)
    # A second signature for nonce 0 bypasses the journal, as a restored or stolen key would.
    other_event = Transfer(
        first.transfer.sender,
        first.transfer.receiver,
        1,
        0,
        (),
        record(wallet, version=1, body={"soc": 0.3}).to_data(),
    )
    second = SignedTransfer.create(wallet.identity, other_event)
    assert ConflictResolver.conflicting(first.transfer, second.transfer)
    assert not ConflictResolver.compatible([first.transfer, second.transfer])
    assert EquivocationProof(first, second).verify()


def test_a_certified_record_needs_a_record_event(wallet):
    from core.attestation import QuorumCertificate

    plain = Transfer(wallet.account, entity_account("e", wallet.asset), 1, 0, (), canonical_data({"x": 1}))
    with pytest.raises(RecordError):
        certified_record(encode_certificate(QuorumCertificate(plain, ())))
    event = sign_record(wallet, record(wallet)).transfer
    found = certified_record(encode_certificate(QuorumCertificate(event, ())))
    assert found.record.entity == "rover-1" and found.event_id == event.event_id()
    assert found.provenance()["body_sha256"] == json.loads(event.data)["body_sha256"]
