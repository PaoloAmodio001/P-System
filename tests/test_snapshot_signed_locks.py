"""The locks a snapshot carries are signed by their sender, as in the reports of a closure.

Before version 2 of the attestation a lock was a bare event. One faulty member among the signers of a
snapshot could add a lock for an event the sender never signed, and every node that took the snapshot
then refused to vote for the real event of that nonce, for good: a blocked honest sender. The model
allows any extra lock (more locks only refuse more votes), so safety was never at stake. Liveness was.

The attack below is written in the two forms a faulty member can try: a bare event, which the wire no
longer takes, and the event signed with its own key, which is not the key of the sender.
"""

import json
import sqlite3
from hashlib import sha256

import pytest

from core.attestation import (
    Committee,
    EpochChange,
    EpochClosure,
    EpochReport,
    Governance,
    QuorumCertificate,
    Snapshot,
    SnapshotAttestation,
    Vote,
)
from core.event import Transfer
from core.signed_event import SignedTransfer
from core.state import State
from crypto.identity import Identity
from network.message import (
    _encode_quorum_event,
    _encode_signed_event,
    encode_snapshot,
)
from network.quorum import QuorumDriver, QuorumReplica, SqliteVoteStore

SENDER = Identity.create()
ALICE = SENDER.identity_id
BOB = Identity.create().identity_id
GENESIS = State({ALICE: 100})
MEMBERS = sorted((Identity.create() for _ in range(4)), key=lambda m: m.public_key)
COMMITTEE = Committee.create([m.public_key for m in MEMBERS], 1, GENESIS)
SIGNERS = [Identity.create() for _ in range(3)]
GOVERNANCE = Governance(tuple(sorted(s.public_key for s in SIGNERS)), 2)
FAULTY = MEMBERS[3]
# What Alice never signed: her nonce 1, to the faulty member.
FAKE = Transfer(ALICE, FAULTY.identity_id, 90, 1)
REAL = Transfer(ALICE, BOB, 5, 1)


def certificate(event: Transfer) -> QuorumCertificate:
    return QuorumCertificate(event, tuple(Vote.create(COMMITTEE, m, event) for m in MEMBERS[:3]), 0)


def open_replica(path, index=0, create=True) -> QuorumReplica:
    store = SqliteVoteStore(path, COMMITTEE, MEMBERS[index].public_key, create=create, governance=GOVERNANCE)
    return QuorumReplica(MEMBERS[index], GENESIS, store, lambda _event: True)


def legacy_signature(member: Identity, digest: str, locks: tuple[Transfer, ...]) -> bytes:
    """The payload of version 1, written out here so that the test does not depend on the code it tests."""
    data = sha256()

    for event in locks:
        canonical = event.canonical()
        data.update(len(canonical).to_bytes(4, "big"))
        data.update(canonical)

    payload = (
        b"P-SYSTEM/SNAPSHOT/v1\0"
        + bytes.fromhex(COMMITTEE.committee_id)
        + bytes.fromhex(digest)
        + data.digest()
    )
    return member.sign(payload)


def attack(replica: QuorumReplica, form: str) -> dict:
    """A snapshot of the true state, signed by two honest members and by the faulty one, with its lock."""
    candidate = replica.candidate_snapshot()
    honest = Snapshot(
        candidate.epoch,
        candidate.state,
        candidate.ids,
        tuple(SnapshotAttestation.create(COMMITTEE, m, candidate.digest, ()) for m in MEMBERS[1:3]),
    )
    message = json.loads(json.dumps(encode_snapshot(honest)))
    index = COMMITTEE.index_of(FAULTY.public_key)

    if form == "bare":
        faulty = {
            "validator": index,
            "locks": [_encode_quorum_event(FAKE)],
            "signature": legacy_signature(FAULTY, candidate.digest, (FAKE,)).hex(),
        }
    else:
        lock = SignedTransfer.create(FAULTY, FAKE)
        payload = SnapshotAttestation._payload(COMMITTEE, candidate.digest, (lock,))
        faulty = {
            "validator": index,
            "locks": [_encode_signed_event(lock)],
            "signature": FAULTY.sign(payload).hex(),
            "version": 2,
        }

    message["snapshot"]["attestations"].append(faulty)
    message["snapshot"]["attestations"].sort(key=lambda item: item["validator"])
    return message


@pytest.mark.parametrize("form", ["bare", "self_signed"])
def test_a_lock_the_sender_never_signed_does_not_block_her(tmp_path, form):
    replica = open_replica(tmp_path / "0.sqlite")
    driver = QuorumDriver(replica)
    assert replica.handle_certificate(certificate(Transfer(ALICE, BOB, 1, 0)))

    try:
        driver.handle_message(attack(replica, form))
    except ValueError:
        pass  # Malformed: the connection closes and nothing is taken.

    assert not replica._store.is_locked_event(FAKE)
    assert replica.handle_vote_request(REAL, SignedTransfer.create(SENDER, REAL)) is not None


def test_a_snapshot_with_a_lock_signed_by_its_sender_is_taken_with_the_lock(tmp_path):
    # The control: the same path takes a lock that Alice did sign, and then refuses the other version.
    replica = open_replica(tmp_path / "0.sqlite")
    driver = QuorumDriver(replica)
    assert replica.handle_certificate(certificate(Transfer(ALICE, BOB, 1, 0)))
    candidate = replica.candidate_snapshot()
    lock = SignedTransfer.create(SENDER, FAKE)
    snapshot = Snapshot(
        candidate.epoch,
        candidate.state,
        candidate.ids,
        tuple(SnapshotAttestation.create(COMMITTEE, m, candidate.digest, (lock,)) for m in MEMBERS[1:4]),
    )

    driver.handle_message(json.loads(json.dumps(encode_snapshot(snapshot))))

    assert replica._store.is_locked_event(FAKE)
    assert replica.handle_vote_request(REAL, SignedTransfer.create(SENDER, REAL)) is None


def test_an_attestation_refuses_a_lock_not_signed_by_its_sender():
    digest = "ab" * 32
    bad = SignedTransfer.create(FAULTY, FAKE)
    good = SignedTransfer.create(SENDER, FAKE)

    assert not SnapshotAttestation.create(COMMITTEE, FAULTY, digest, (bad,)).verify(COMMITTEE, digest)
    assert SnapshotAttestation.create(COMMITTEE, FAULTY, digest, (good,)).verify(COMMITTEE, digest)

    with pytest.raises(ValueError):
        SnapshotAttestation.create(COMMITTEE, FAULTY, digest, (FAKE,))


def test_a_legacy_attestation_is_read_only_from_the_file_of_the_node():
    digest = "cd" * 32
    legacy = SnapshotAttestation(
        COMMITTEE.index_of(MEMBERS[0].public_key),
        (FAKE,),
        legacy_signature(MEMBERS[0], digest, (FAKE,)),
        version=1,
    )

    assert legacy.verify(COMMITTEE, digest, allow_legacy=True)
    assert not legacy.verify(COMMITTEE, digest)


# --- The store, from schema 5 to schema 6 ---------------------------------------------------------


def closure_locking(event_signed: SignedTransfer) -> EpochClosure:
    change = EpochChange.create(COMMITTEE, [m.public_key for m in MEMBERS], 1, GOVERNANCE, SIGNERS[:2])
    reports = tuple(
        sorted(
            (EpochReport.create(COMMITTEE, m, change.change_id, (event_signed,)) for m in MEMBERS[:3]),
            key=lambda report: report.validator,
        )
    )
    return EpochClosure(change, reports)


def as_schema_5(path) -> None:
    """What a file of schema 5 looked like: locks without signatures."""
    connection = sqlite3.connect(path)
    connection.execute("ALTER TABLE locks DROP COLUMN public_key")
    connection.execute("ALTER TABLE locks DROP COLUMN signature")
    connection.execute("UPDATE meta SET value = '5' WHERE key = 'schema_version'")
    connection.commit()
    connection.close()


def test_a_store_of_schema_5_gets_the_signatures_its_closures_hold(tmp_path):
    path = tmp_path / "0.sqlite"
    store = SqliteVoteStore(path, COMMITTEE, MEMBERS[0].public_key, create=True, governance=GOVERNANCE)
    signed = SignedTransfer.create(SENDER, FAKE)
    store.install_closure(closure_locking(signed))
    store.close()
    as_schema_5(path)

    store = SqliteVoteStore(path, COMMITTEE, MEMBERS[0].public_key, governance=GOVERNANCE)

    assert store.locks_over({}) == [signed]
    assert store.is_locked_event(FAKE)
    store.close()


def test_a_lock_of_schema_5_with_no_signature_still_refuses_and_signs_no_snapshot(tmp_path):
    path = tmp_path / "0.sqlite"
    store = SqliteVoteStore(path, COMMITTEE, MEMBERS[0].public_key, create=True)
    store.close()
    as_schema_5(path)
    connection = sqlite3.connect(path)
    connection.execute(
        "INSERT INTO locks (sender, nonce, canonical) VALUES (?, ?, ?)",
        (ALICE, "1", FAKE.canonical().decode()),
    )
    connection.commit()
    connection.close()

    replica = QuorumReplica(MEMBERS[0], GENESIS, SqliteVoteStore(path, COMMITTEE, MEMBERS[0].public_key), lambda _e: True)

    assert replica.handle_vote_request(REAL, SignedTransfer.create(SENDER, REAL)) is None
    assert replica._store.locks_over({}) is None
    candidate = replica.candidate_snapshot()
    assert replica.attest_snapshot(candidate.epoch, candidate.digest, candidate.state.nonces) is None
    # A floor past it: the lock no longer counts, and the member signs again.
    assert replica._store.locks_over({ALICE: 2}) == []


def test_a_snapshot_of_version_1_on_file_still_opens(tmp_path):
    path = tmp_path / "0.sqlite"
    replica = open_replica(path)
    assert replica.handle_certificate(certificate(Transfer(ALICE, BOB, 1, 0)))
    candidate = replica.candidate_snapshot()
    body = {
        "epoch": candidate.epoch,
        "balances": dict(sorted(candidate.state.balances.items())),
        "nonces": dict(sorted(candidate.state.nonces.items())),
        "ids": list(candidate.ids),
        "attestations": [
            {
                "validator": COMMITTEE.index_of(m.public_key),
                "locks": [],
                "signature": legacy_signature(m, candidate.digest, ()).hex(),
            }
            for m in sorted(MEMBERS[:3], key=lambda m: COMMITTEE.index_of(m.public_key))
        ],
    }
    replica._store._connection.execute(
        "INSERT OR REPLACE INTO snapshot (id, body) VALUES (1, ?)", (json.dumps(body),)
    )
    replica._store.close()

    again = open_replica(path, create=False)

    assert again.base is not None and again.base.is_legacy
    assert again.state.root() == candidate.state.root()
    # Never sent to a peer, which would refuse it.
    assert QuorumDriver(again)._snapshot_for({}) == ()


def test_a_bare_lock_in_version_2_is_refused_without_an_exception():
    digest = "ef" * 32
    bare = SnapshotAttestation(
        COMMITTEE.index_of(FAULTY.public_key),
        (FAKE,),
        legacy_signature(FAULTY, digest, (FAKE,)),
    )

    assert bare.verify(COMMITTEE, digest) is False
