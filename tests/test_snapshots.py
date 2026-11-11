"""Snapshots and pruning (formal/lean/PSystem/QuorumSnapshot.lean), with no network but the last tests.

The rules a mutation can break: who signs, what a node takes from others, what pruning removes, and
the floor that must come with a pruned lock. Python and Lean are compared in
tests/test_quorum_differential.py, where the replica restarts from a snapshot at random points.
"""

import json
import logging
import sqlite3
import time

import pytest

from core.attestation import (
    Committee,
    EpochChange,
    EpochClosure,
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
    decode_snapshot,
    decode_snapshot_request,
    decode_snapshot_vote,
    encode_certificate,
    encode_certificate_sync,
    encode_snapshot,
    encode_snapshot_request,
    encode_snapshot_vote,
    encode_vote_request,
)
from network.node import Node
from network.peer import Peer
from network.quorum import (
    QuorumConfig,
    QuorumDriver,
    QuorumReplica,
    SqliteVoteStore,
    VoteStoreError,
)

SENDER = Identity.create()
ALICE = SENDER.identity_id
OTHER = Identity.create()
BOB = OTHER.identity_id
GENESIS = State({ALICE: 100})
MEMBERS = sorted((Identity.create() for _ in range(4)), key=lambda m: m.public_key)
COMMITTEE = Committee.create([m.public_key for m in MEMBERS], 1, GENESIS)
SIGNERS = [Identity.create() for _ in range(3)]
GOVERNANCE = Governance(tuple(sorted(s.public_key for s in SIGNERS)), 2)


def wire(message: dict) -> dict:
    return json.loads(json.dumps(message))


def transfer(nonce: int, amount: int = 1, receiver: str = BOB) -> Transfer:
    return Transfer(ALICE, receiver, amount, nonce)


def lock(nonce: int, receiver: str = BOB) -> SignedTransfer:
    """A lock as a snapshot carries it: signed by its sender."""
    return SignedTransfer.create(SENDER, transfer(nonce, receiver=receiver))


def signed_by(identity: Identity, event: Transfer) -> SignedTransfer:
    return SignedTransfer.create(identity, event)


def certificate(event: Transfer, epoch: int = 0, committee: Committee = COMMITTEE, members=MEMBERS):
    # Every member: a decision of round 0, which executes.
    votes = tuple(Vote.create(committee, member, event) for member in members[: committee.n])
    return QuorumCertificate(event, votes, epoch)


def open_replica(path, index=0, create=True) -> QuorumReplica:
    store = SqliteVoteStore(
        path,
        COMMITTEE,
        MEMBERS[index].public_key,
        create=create,
        governance=GOVERNANCE,
    )
    return QuorumReplica(MEMBERS[index], GENESIS, store, lambda _event: True)


def attested(replica: QuorumReplica, signers=MEMBERS[:3], committee=None, locks=()) -> Snapshot:
    """The state of `replica`, signed by members directly: what a quorum would give."""
    candidate = replica.candidate_snapshot()
    committee = committee or replica.committee
    return Snapshot(
        candidate.epoch,
        candidate.state,
        candidate.ids,
        tuple(
            sorted(
                (
                    SnapshotAttestation.create(committee, member, candidate.digest, locks)
                    for member in signers
                ),
                key=lambda attestation: attestation.validator,
            )
        ),
    )


@pytest.fixture
def replica(tmp_path):
    made = open_replica(tmp_path / "0.sqlite")
    yield made
    made._store.close()


def run(replica, *events):
    for event in events:
        assert replica.handle_certificate(certificate(event))


# --- The value ----------------------------------------------------------------------------------


def test_a_quorum_of_signatures_verifies(replica):
    run(replica, transfer(0))
    assert attested(replica).verify(COMMITTEE)


def test_below_a_quorum_it_does_not(replica):
    run(replica, transfer(0))
    assert not attested(replica, MEMBERS[:2]).verify(COMMITTEE)


def test_one_member_twice_counts_once(replica):
    run(replica, transfer(0))
    snapshot = attested(replica, MEMBERS[:2])
    twice = Snapshot(
        snapshot.epoch,
        snapshot.state,
        snapshot.ids,
        (*snapshot.attestations, snapshot.attestations[0]),
    )
    assert not twice.verify(COMMITTEE)


def test_a_signature_of_someone_outside_the_committee_does_not_count(replica):
    run(replica, transfer(0))
    outsider = Identity.create()
    good = attested(replica, MEMBERS[:2])
    forged = SnapshotAttestation(
        2,
        (),
        outsider.sign(SnapshotAttestation._payload(COMMITTEE, good.digest, ())),
    )
    assert not Snapshot(
        good.epoch,
        good.state,
        good.ids,
        (*good.attestations, forged),
    ).verify(COMMITTEE)


def test_a_changed_balance_breaks_every_signature(replica):
    run(replica, transfer(0))
    good = attested(replica)
    state = good.state.copy()
    state.balances[BOB] += 1000
    assert not Snapshot(good.epoch, state, good.ids, good.attestations).verify(COMMITTEE)


def test_changed_ids_break_every_signature(replica):
    run(replica, transfer(0))
    good = attested(replica)
    assert not Snapshot(good.epoch, good.state, (), good.attestations).verify(COMMITTEE)


def test_the_locks_of_a_signer_are_under_its_signature(replica):
    run(replica, transfer(0))
    good = attested(replica, locks=(lock(9),))
    first = good.attestations[0]
    changed = SnapshotAttestation(first.validator, (), first.signature)
    assert not Snapshot(
        good.epoch,
        good.state,
        good.ids,
        (changed, *good.attestations[1:]),
    ).verify(COMMITTEE)


def test_the_signature_of_another_committee_does_not_count(replica):
    run(replica, transfer(0))
    other = Committee.create([m.public_key for m in MEMBERS], 1, State({ALICE: 7}))
    assert not attested(replica, committee=other).verify(COMMITTEE)


def test_a_signature_says_nothing_of_another_epoch(replica):
    run(replica, transfer(0))
    good = attested(replica)
    assert not Snapshot(good.epoch + 1, good.state, good.ids, good.attestations).verify(COMMITTEE)


def test_someone_outside_the_committee_cannot_make_one(replica):
    with pytest.raises(ValueError, match="NOT A COMMITTEE MEMBER"):
        SnapshotAttestation.create(COMMITTEE, Identity.create(), "ab" * 32, ())


def test_ids_out_of_order_or_repeated_are_refused(replica):
    run(replica, transfer(0), transfer(1))
    good = attested(replica)
    for ids in (tuple(reversed(good.ids)), (good.ids[0], good.ids[0])):
        snapshot = Snapshot(good.epoch, good.state, ids)
        signed = Snapshot(
            good.epoch,
            good.state,
            ids,
            tuple(
                SnapshotAttestation.create(COMMITTEE, member, snapshot.digest, ())
                for member in MEMBERS[:3]
            ),
        )
        assert not signed.verify(COMMITTEE)


def test_the_locks_are_the_union_of_those_of_the_signers(replica):
    run(replica, transfer(0))
    candidate = replica.candidate_snapshot()
    one, two = lock(5), lock(6)
    snapshot = Snapshot(
        candidate.epoch,
        candidate.state,
        candidate.ids,
        (
            SnapshotAttestation.create(COMMITTEE, MEMBERS[0], candidate.digest, (one,)),
            SnapshotAttestation.create(COMMITTEE, MEMBERS[1], candidate.digest, (two,)),
            SnapshotAttestation.create(COMMITTEE, MEMBERS[2], candidate.digest, (one, two)),
        ),
    )
    assert snapshot.verify(COMMITTEE)
    assert set(snapshot.locks()) == {one, two}


def test_it_goes_through_the_wire_unchanged(replica):
    run(replica, transfer(0))
    snapshot = attested(replica, locks=(lock(3),))
    decoded = decode_snapshot(wire(encode_snapshot(snapshot)))
    assert decoded == snapshot
    assert decoded.verify(COMMITTEE)


@pytest.mark.parametrize(
    "change",
    [
        lambda m: m["snapshot"].update(extra=1),
        lambda m: m["snapshot"].pop("ids"),
        lambda m: m["snapshot"].update(epoch=-1),
        lambda m: m["snapshot"].update(epoch="0"),
        lambda m: m["snapshot"].update(ids="x"),
        lambda m: m["snapshot"].update(ids=["zz"]),
        lambda m: m["snapshot"].update(balances=[]),
        lambda m: m["snapshot"]["balances"].update(x=-1),
        lambda m: m["snapshot"]["nonces"].update(x="1"),
        lambda m: m["snapshot"].update(attestations={}),
        lambda m: m["snapshot"]["attestations"][0].update(signature="00"),
        lambda m: m["snapshot"]["attestations"][0].update(validator=-1),
        lambda m: m["snapshot"]["attestations"][0].update(locks={}),
        # A lock is a signed event, and the version is 2: the form before it comes from no peer.
        lambda m: m["snapshot"]["attestations"][0].pop("version"),
        lambda m: m["snapshot"]["attestations"][0].update(version=1),
        lambda m: m["snapshot"]["attestations"][0].update(version=True),
        lambda m: m["snapshot"]["attestations"][0].update(locks=[{"sender": "a", "receiver": "b", "amount": 1, "nonce": 0, "parents": []}]),
    ],
)
def test_a_malformed_snapshot_is_refused_by_the_decoder(replica, change):
    run(replica, transfer(0))
    message = wire(encode_snapshot(attested(replica)))
    change(message)
    with pytest.raises(ValueError):
        decode_snapshot(message)


def test_requests_and_votes_go_through_the_wire(replica):
    run(replica, transfer(0))
    candidate = replica.candidate_snapshot()
    nonces = candidate.state.nonces
    assert decode_snapshot_request(
        wire(encode_snapshot_request(0, candidate.digest, nonces))
    ) == (0, candidate.digest, nonces)
    attestation = SnapshotAttestation.create(COMMITTEE, MEMBERS[0], candidate.digest, ())
    assert decode_snapshot_vote(wire(encode_snapshot_vote(candidate.digest, attestation))) == (
        candidate.digest,
        attestation,
    )


# --- Who signs ----------------------------------------------------------------------------------


def request_for(replica):
    candidate = replica.candidate_snapshot()
    return candidate.epoch, candidate.digest, candidate.state.nonces


def test_a_member_with_the_same_events_signs(tmp_path):
    first, second = open_replica(tmp_path / "1.sqlite"), open_replica(tmp_path / "2.sqlite", 1)
    run(first, transfer(0), transfer(1))
    run(second, transfer(0), transfer(1))
    attestation = second.attest_snapshot(*request_for(first))
    assert attestation is not None
    assert attestation.verify(COMMITTEE, first.candidate_snapshot().digest)
    assert attestation.validator == 1


def test_a_member_behind_does_not_sign(tmp_path):
    first, second = open_replica(tmp_path / "1.sqlite"), open_replica(tmp_path / "2.sqlite", 1)
    run(first, transfer(0), transfer(1))
    run(second, transfer(0))
    assert second.attest_snapshot(*request_for(first)) is None


def test_a_member_ahead_signs_what_it_has_passed(tmp_path):
    first, second = open_replica(tmp_path / "1.sqlite"), open_replica(tmp_path / "2.sqlite", 1)
    run(first, transfer(0))
    run(second, transfer(0), transfer(1))
    assert second.attest_snapshot(*request_for(first)) is not None


def test_a_member_does_not_sign_a_state_it_cannot_derive(tmp_path):
    first, second = open_replica(tmp_path / "1.sqlite"), open_replica(tmp_path / "2.sqlite", 1)
    run(first, transfer(0, receiver="carol"))
    run(second, transfer(0, receiver="dave"))
    assert second.attest_snapshot(*request_for(first)) is None


def test_a_member_does_not_sign_a_digest_that_does_not_match(tmp_path):
    first = open_replica(tmp_path / "1.sqlite")
    run(first, transfer(0))
    epoch, _, nonces = request_for(first)
    assert first.attest_snapshot(epoch, "ab" * 32, nonces) is None


def test_a_part_of_a_valid_order_can_need_another_order(tmp_path):
    # Bob spends what he got. The member ran a third event in between, which the snapshot leaves out,
    # so the part of its log has to be run in another order than it stands.
    first, second = open_replica(tmp_path / "1.sqlite"), open_replica(tmp_path / "2.sqlite", 1)
    pay_bob = transfer(0, 5)
    bob_pays = Transfer(BOB, "carol", 3, 0)
    alice_again = transfer(1, 1)
    run(first, pay_bob, bob_pays)
    run(second, pay_bob, alice_again, bob_pays)
    assert second.attest_snapshot(*request_for(first)) is not None


def test_a_part_of_a_valid_order_can_need_several_passes(tmp_path):
    # Bob pays from what Alice gave him in an event the snapshot leaves out, so in the log of this
    # member he pays before he gets what the snapshot counts on, and that takes a second pass.
    first, second = open_replica(tmp_path / "1.sqlite"), open_replica(tmp_path / "2.sqlite", 1)
    to_carol = transfer(0, 5, "carol")
    carol_pays_bob = Transfer("carol", BOB, 5, 0)
    bob_pays = Transfer(BOB, "dave", 5, 0)
    alice_pays_bob = transfer(1, 5)
    run(first, to_carol, carol_pays_bob, bob_pays)
    run(second, to_carol, alice_pays_bob, bob_pays, carol_pays_bob)
    assert second.attest_snapshot(*request_for(first)) is not None


def test_a_member_does_not_sign_an_event_without_its_parent(tmp_path):
    second = open_replica(tmp_path / "2.sqlite", 1)
    pay_bob = transfer(0, 5)
    parent = transfer(1)
    child = Transfer(BOB, "carol", 1, 0, (parent.event_id(),))
    run(second, pay_bob, parent, child)
    # A state with the child and not its parent. Its balances are right: only the parent is missing.
    state = GENESIS.copy()
    for event in (pay_bob, child):
        from core.derive import StateDeriver

        StateDeriver._apply_one(state, event)
    ids = tuple(sorted({pay_bob.event_id(), child.event_id()}))
    assert (
        second.attest_snapshot(0, Snapshot(0, state, ids).digest, dict(state.nonces)) is None
    )


def test_someone_outside_the_committee_does_not_sign(tmp_path):
    outsider = Identity.create()
    store = SqliteVoteStore(
        tmp_path / "out.sqlite",
        COMMITTEE,
        outsider.public_key,
        create=True,
        joining=True,
    )
    replica = QuorumReplica(outsider, GENESIS, store, lambda _event: True)
    assert replica.attest_snapshot(*request_for(replica)) is None


def test_no_signature_for_another_epoch(replica):
    run(replica, transfer(0))
    epoch, digest, nonces = request_for(replica)
    assert replica.attest_snapshot(epoch + 1, digest, nonces) is None


def test_a_halted_member_does_not_sign(replica):
    run(replica, transfer(0))
    replica.record_halt(certificate(transfer(1, receiver="x")), certificate(transfer(1, receiver="y")))
    assert replica.attest_snapshot(*request_for(replica)) is None


def test_a_member_that_pruned_past_it_cannot_recompute(tmp_path):
    first, second = open_replica(tmp_path / "1.sqlite"), open_replica(tmp_path / "2.sqlite", 1)
    run(first, transfer(0))
    old = request_for(first)
    run(second, transfer(0), transfer(1))
    assert second.install_snapshot(attested(second))
    second.prune_covered()
    assert second.attest_snapshot(*old) is None


def test_a_member_that_pruned_signs_its_own_base(tmp_path):
    second = open_replica(tmp_path / "2.sqlite", 1)
    run(second, transfer(0))
    base = attested(second)
    assert second.install_snapshot(base)
    second.prune_covered()
    assert second.attest_snapshot(base.epoch, base.digest, base.state.nonces) is not None


def test_a_signer_reports_only_the_locks_over_the_floor(replica):
    store = replica._store
    store._begin()
    store._add_locks([lock(0), lock(5)])
    store._commit()
    assert store.locks_over({ALICE: 1}) == [lock(5)]
    assert sorted(e.transfer.nonce for e in store.locks_over({})) == [0, 5]


# --- A restart ----------------------------------------------------------------------------------


def corrupt_signature(path, event):
    connection = sqlite3.connect(path)
    connection.execute(
        "UPDATE certificates SET signatures = ? WHERE event_id = ?",
        (json.dumps([[0, "00" * 64], [1, "00" * 64], [2, "00" * 64]]), event.event_id()),
    )
    connection.commit()
    connection.close()


def test_a_restart_gives_the_same_state_as_replaying_all(tmp_path):
    path = tmp_path / "1.sqlite"
    replica = open_replica(path)
    events = [transfer(n) for n in range(5)]
    run(replica, *events[:3])
    assert replica.install_snapshot(attested(replica))
    run(replica, *events[3:])
    root = replica.state.root()
    replica._store.close()

    again = open_replica(path, create=False)
    assert again.state.root() == root
    assert [c.event for c in again.log] == events
    assert again.base is not None
    run(again, transfer(5))
    again._store.close()


def test_a_restart_does_not_read_the_signatures_the_snapshot_covers(tmp_path):
    path = tmp_path / "1.sqlite"
    replica = open_replica(path)
    run(replica, transfer(0))
    assert replica.install_snapshot(attested(replica))
    replica._store.close()
    corrupt_signature(path, transfer(0))

    open_replica(path, create=False)._store.close()


def test_a_restart_reads_the_signatures_after_the_snapshot(tmp_path):
    path = tmp_path / "1.sqlite"
    replica = open_replica(path)
    run(replica, transfer(0))
    assert replica.install_snapshot(attested(replica))
    run(replica, transfer(1))
    replica._store.close()
    corrupt_signature(path, transfer(1))

    with pytest.raises(VoteStoreError, match="DOES NOT REPLAY"):
        open_replica(path, create=False)


def test_without_a_snapshot_a_restart_reads_them_all(tmp_path):
    path = tmp_path / "1.sqlite"
    replica = open_replica(path)
    run(replica, transfer(0))
    replica._store.close()
    corrupt_signature(path, transfer(0))

    with pytest.raises(VoteStoreError, match="DOES NOT REPLAY"):
        open_replica(path, create=False)


def alter_snapshot(path, change):
    connection = sqlite3.connect(path)
    body = json.loads(connection.execute("SELECT body FROM snapshot").fetchone()[0])
    change(body)
    connection.execute("UPDATE snapshot SET body = ?", (json.dumps(body),))
    connection.commit()
    connection.close()


def test_an_altered_snapshot_does_not_open(tmp_path):
    path = tmp_path / "1.sqlite"
    replica = open_replica(path)
    run(replica, transfer(0))
    assert replica.install_snapshot(attested(replica))
    replica._store.close()
    alter_snapshot(path, lambda body: body["balances"].update({BOB: 1000}))

    with pytest.raises(VoteStoreError, match="SNAPSHOT DOES NOT VERIFY"):
        open_replica(path, create=False)


def test_an_unreadable_snapshot_does_not_open(tmp_path):
    path = tmp_path / "1.sqlite"
    replica = open_replica(path)
    run(replica, transfer(0))
    assert replica.install_snapshot(attested(replica))
    replica._store.close()
    alter_snapshot(path, lambda body: body.pop("ids"))

    with pytest.raises(VoteStoreError, match="UNREADABLE"):
        open_replica(path, create=False)


def test_a_log_row_the_snapshot_does_not_hold_does_not_open(tmp_path):
    path = tmp_path / "1.sqlite"
    replica = open_replica(path)
    run(replica, transfer(0))
    assert replica.install_snapshot(attested(replica))
    replica._store.close()
    other = transfer(0, receiver="carol")
    connection = sqlite3.connect(path)
    connection.execute(
        "UPDATE certificates SET event_id = ?, canonical = ?",
        (other.event_id(), other.canonical().decode()),
    )
    connection.commit()
    connection.close()

    with pytest.raises(VoteStoreError, match="DOES NOT FIT"):
        open_replica(path, create=False)


# --- Taking one from others ---------------------------------------------------------------------


def test_a_node_behind_takes_the_state_and_goes_on(tmp_path):
    ahead, behind = open_replica(tmp_path / "1.sqlite"), open_replica(tmp_path / "2.sqlite", 1)
    run(ahead, transfer(0), transfer(1))
    assert behind.install_snapshot(attested(ahead))
    assert behind.state.root() == ahead.state.root()
    run(behind, transfer(2))
    run(ahead, transfer(2))
    assert behind.state.root() == ahead.state.root()


def test_a_node_keeps_what_it_has_beyond_the_snapshot(tmp_path):
    ahead, other = open_replica(tmp_path / "1.sqlite"), open_replica(tmp_path / "2.sqlite", 1)
    bob_pays = Transfer(BOB, "carol", 1, 0)
    run(ahead, transfer(0, 5), transfer(1))
    run(other, transfer(0, 5), bob_pays)
    assert other.install_snapshot(attested(ahead))
    run(ahead, bob_pays)
    assert other.state.root() == ahead.state.root()
    assert [c.event for c in other.log] == [transfer(0, 5), bob_pays]


def test_a_child_of_an_event_only_in_the_snapshot_can_run(tmp_path):
    ahead, behind = open_replica(tmp_path / "1.sqlite"), open_replica(tmp_path / "2.sqlite", 1)
    parent = transfer(0)
    run(ahead, parent)
    assert behind.install_snapshot(attested(ahead))
    run(behind, Transfer(ALICE, BOB, 1, 1, (parent.event_id(),)))


def test_an_event_inside_the_snapshot_does_not_run_again(tmp_path):
    ahead, behind = open_replica(tmp_path / "1.sqlite"), open_replica(tmp_path / "2.sqlite", 1)
    run(ahead, transfer(0))
    assert behind.install_snapshot(attested(ahead))
    assert not behind.handle_certificate(certificate(transfer(0)))


def test_a_snapshot_without_a_quorum_is_refused(tmp_path):
    ahead, behind = open_replica(tmp_path / "1.sqlite"), open_replica(tmp_path / "2.sqlite", 1)
    run(ahead, transfer(0))
    assert not behind.install_snapshot(attested(ahead, MEMBERS[:2]))
    assert behind.state.root() == GENESIS.root()
    assert behind.base is None


def test_a_snapshot_that_lacks_an_event_this_node_ran_is_refused(tmp_path, caplog):
    # A quorum signed a state without an event this node holds: more than `f` faulty.
    ahead, other = open_replica(tmp_path / "1.sqlite"), open_replica(tmp_path / "2.sqlite", 1)
    run(ahead, transfer(0, receiver="carol"))
    run(other, transfer(0, receiver="dave"))
    root = other.state.root()

    with caplog.at_level(logging.CRITICAL, logger="psystem.quorum"):
        assert not other.install_snapshot(attested(ahead))

    assert other.state.root() == root
    assert other.base is None
    assert "does not hold an event" in caplog.text


def test_a_log_that_does_not_run_after_the_snapshot_is_refused(tmp_path, caplog):
    # The snapshot says this sender has spent everything, against what this node ran next.
    ahead, other = open_replica(tmp_path / "1.sqlite"), open_replica(tmp_path / "2.sqlite", 1)
    spend_all = transfer(0, 100)
    run(ahead, spend_all)
    run(other, spend_all)
    bob_pays = Transfer(BOB, "carol", 100, 0)
    run(other, bob_pays)
    state = ahead.state.copy()
    state.balances[BOB] = 0
    candidate = Snapshot(0, state, ahead.candidate_snapshot().ids)
    forged = Snapshot(
        0,
        state,
        candidate.ids,
        tuple(
            SnapshotAttestation.create(COMMITTEE, member, candidate.digest, ())
            for member in MEMBERS[:3]
        ),
    )

    with caplog.at_level(logging.CRITICAL, logger="psystem.quorum"):
        assert not other.install_snapshot(forged)

    assert "does not run after" in caplog.text


def test_a_count_of_ids_that_does_not_fit_the_nonces_is_refused(tmp_path):
    ahead, behind = open_replica(tmp_path / "1.sqlite"), open_replica(tmp_path / "2.sqlite", 1)
    run(ahead, transfer(0), transfer(1))
    good = ahead.candidate_snapshot()
    short = Snapshot(0, good.state, good.ids[:1])
    signed = Snapshot(
        0,
        good.state,
        good.ids[:1],
        tuple(
            SnapshotAttestation.create(COMMITTEE, member, short.digest, ())
            for member in MEMBERS[:3]
        ),
    )
    assert signed.verify(COMMITTEE)
    assert not behind.install_snapshot(signed)


def test_an_older_snapshot_does_not_replace_a_newer_one(tmp_path):
    ahead, behind = open_replica(tmp_path / "1.sqlite"), open_replica(tmp_path / "2.sqlite", 1)
    run(ahead, transfer(0))
    older = attested(ahead)
    run(ahead, transfer(1))
    newer = attested(ahead)
    assert behind.install_snapshot(newer)
    assert not behind.install_snapshot(older)
    assert behind.base.digest == newer.digest


def test_the_same_snapshot_again_is_nothing_new(tmp_path):
    ahead, behind = open_replica(tmp_path / "1.sqlite"), open_replica(tmp_path / "2.sqlite", 1)
    run(ahead, transfer(0))
    snapshot = attested(ahead)
    assert behind.install_snapshot(snapshot)
    assert not behind.install_snapshot(snapshot)


# --- Epochs -------------------------------------------------------------------------------------


NEXT = sorted((Identity.create() for _ in range(4)), key=lambda m: m.public_key)


def next_epoch(replica) -> Committee:
    """Install a closure into the next epoch, with this event locked."""
    current = replica.committee
    change = EpochChange.create(current, [m.public_key for m in NEXT], 1, GOVERNANCE, SIGNERS[:2])
    reports = []

    for member in MEMBERS[:3]:
        from core.attestation import EpochReport

        reports.append(EpochReport.create(current, member, change.change_id, ()))

    closure = EpochClosure(change, tuple(sorted(reports, key=lambda r: r.validator)))
    assert closure.verify(GOVERNANCE, current)
    replica.install_closure(closure)
    return replica.committee


def test_a_snapshot_of_an_ended_committee_is_refused(tmp_path):
    # Its keys can be stolen: the same reason as for an old certificate.
    ahead, behind = open_replica(tmp_path / "1.sqlite"), open_replica(tmp_path / "2.sqlite", 1)
    run(ahead, transfer(0))
    old = attested(ahead)
    next_epoch(behind)
    assert not behind.install_snapshot(old)
    assert behind.base is None


def test_a_snapshot_of_the_committee_in_force_is_taken_after_a_change(tmp_path):
    ahead, behind = open_replica(tmp_path / "1.sqlite"), open_replica(tmp_path / "2.sqlite", 1)
    run(ahead, transfer(0))
    next_epoch(ahead)
    committee = next_epoch(behind)
    assert behind.install_snapshot(attested(ahead, NEXT[:3], committee))
    assert behind.state.root() == ahead.state.root()


def test_a_snapshot_of_an_earlier_epoch_opens_from_its_own_file(tmp_path):
    path = tmp_path / "1.sqlite"
    replica = open_replica(path)
    run(replica, transfer(0))
    assert replica.install_snapshot(attested(replica))
    next_epoch(replica)
    root = replica.state.root()
    replica._store.close()

    again = open_replica(path, create=False)
    assert again.state.root() == root
    assert again.base.epoch == 0
    again._store.close()


# --- Pruning ------------------------------------------------------------------------------------


def certificate_rows(path) -> int:
    connection = sqlite3.connect(path)
    count = connection.execute("SELECT COUNT(*) FROM certificates").fetchone()[0]
    connection.close()
    return count


def table_rows(path, table) -> int:
    connection = sqlite3.connect(path)
    count = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    connection.close()
    return count


def driver_of(replica, **kwargs) -> QuorumDriver:
    return QuorumDriver(replica, GOVERNANCE, **kwargs)


def take(driver, snapshot):
    return driver.handle_message(wire(encode_snapshot(snapshot)))


def test_pruning_removes_what_the_snapshot_covers_and_only_that(tmp_path):
    path = tmp_path / "1.sqlite"
    replica = open_replica(path)
    driver = driver_of(replica, prune=True)
    run(replica, transfer(0), transfer(1))
    snapshot = attested(replica)
    run(replica, transfer(2))
    take(driver, snapshot)
    assert [c.event for c in replica.log] == [transfer(2)]
    assert certificate_rows(path) == 1
    replica._store.close()

    again = open_replica(path, create=False)
    assert again.state.nonce(ALICE) == 3
    assert [c.event for c in again.log] == [transfer(2)]
    again._store.close()


def test_without_the_setting_nothing_is_removed(tmp_path):
    path = tmp_path / "1.sqlite"
    replica = open_replica(path)
    driver = driver_of(replica)
    run(replica, transfer(0))
    take(driver, attested(replica))
    assert certificate_rows(path) == 1
    replica._store.close()


def test_a_certificate_inside_a_pruned_snapshot_is_ignored_with_no_noise(tmp_path, caplog):
    replica = open_replica(tmp_path / "1.sqlite")
    driver = driver_of(replica, prune=True)
    run(replica, transfer(0))
    take(driver, attested(replica))

    with caplog.at_level(logging.CRITICAL, logger="psystem.quorum"):
        driver.handle_message(wire(encode_certificate(certificate(transfer(0)))))

    assert not driver._buffer
    assert not driver.halted
    assert "conflicts" not in caplog.text


def test_a_conflict_with_a_pruned_event_is_reported_and_stays_out(tmp_path, caplog):
    replica = open_replica(tmp_path / "1.sqlite")
    driver = driver_of(replica, prune=True)
    run(replica, transfer(0))
    take(driver, attested(replica))
    root = replica.state.root()

    with caplog.at_level(logging.CRITICAL, logger="psystem.quorum"):
        driver.handle_message(
            wire(encode_certificate(certificate(transfer(0, receiver="carol"))))
        )

    assert "conflicts with a snapshot" in caplog.text
    assert not driver._buffer
    assert replica.state.root() == root


def test_a_batch_with_pruned_certificates_costs_no_signature(tmp_path, monkeypatch):
    replica = open_replica(tmp_path / "1.sqlite")
    driver = driver_of(replica, prune=True)
    run(replica, transfer(0))
    take(driver, attested(replica))
    calls = []
    monkeypatch.setattr(
        replica,
        "certificate_is_valid",
        lambda certificate: calls.append(certificate) or True,
    )
    driver.handle_message(wire(encode_certificate_sync([certificate(transfer(0))])))
    assert calls == []


def test_a_waiting_certificate_the_snapshot_covers_leaves_the_buffer(tmp_path):
    replica = open_replica(tmp_path / "1.sqlite")
    driver = driver_of(replica)
    ahead = open_replica(tmp_path / "2.sqlite", 1)
    run(ahead, transfer(0), transfer(1))
    driver.handle_message(wire(encode_certificate(certificate(transfer(1)))))
    assert driver._buffer
    take(driver, attested(ahead))
    assert not driver._buffer


def test_the_buffer_runs_after_a_snapshot(tmp_path):
    replica = open_replica(tmp_path / "1.sqlite")
    driver = driver_of(replica)
    ahead = open_replica(tmp_path / "2.sqlite", 1)
    run(ahead, transfer(0))
    driver.handle_message(wire(encode_certificate(certificate(transfer(1)))))
    assert driver._buffer
    take(driver, attested(ahead))
    assert not driver._buffer
    assert replica.state.nonce(ALICE) == 2


# --- The floor ----------------------------------------------------------------------------------


def lock_rows(path):
    connection = sqlite3.connect(path)
    rows = connection.execute("SELECT nonce FROM locks ORDER BY nonce").fetchall()
    connection.close()
    return [row[0] for row in rows]


def test_a_floor_removes_the_locks_under_it_and_refuses_votes_under_it(tmp_path):
    path = tmp_path / "1.sqlite"
    replica = open_replica(path)
    store = replica._store
    run(replica, transfer(0))
    store._begin()
    store._add_locks([lock(0), lock(5)])
    store._commit()
    assert replica.install_snapshot(attested(replica))
    replica.apply_floor()
    assert lock_rows(path) == ["5"]

    # Under the floor: refused, also a version nobody voted for. Without the floor the lock is gone
    # and this vote would pass: `prune_without_floor_lets_conflict_through`.
    assert not store.record_vote(transfer(0, receiver="carol"))
    # A lock over the floor still binds.
    assert not store.record_vote(transfer(5, receiver="carol"))
    assert store.record_vote(transfer(5))
    # Right at the floor is over it: that nonce has not been used.
    assert store.record_vote(transfer(1))
    store.close()


def test_a_snapshot_brings_the_locks_of_its_signers(tmp_path):
    # `union_locks_cover`: a validator that lacks the closures gets them here.
    ahead, behind = open_replica(tmp_path / "1.sqlite"), open_replica(tmp_path / "2.sqlite", 1)
    run(ahead, transfer(0))
    assert behind.install_snapshot(attested(ahead, locks=(lock(5),)))
    assert not behind._store.record_vote(transfer(5, receiver="carol"))
    assert behind._store.record_vote(transfer(5))


def test_a_floor_survives_a_restart(tmp_path):
    path = tmp_path / "1.sqlite"
    replica = open_replica(path)
    run(replica, transfer(0))
    assert replica.install_snapshot(attested(replica))
    replica.apply_floor()
    replica._store.close()

    again = open_replica(path, create=False)
    assert not again._store.record_vote(transfer(0, receiver="carol"))
    again._store.close()


def test_a_floor_for_one_sender_says_nothing_of_another(tmp_path):
    replica = open_replica(tmp_path / "1.sqlite")
    run(replica, transfer(0))
    assert replica.install_snapshot(attested(replica))
    replica.apply_floor()
    assert replica._store.record_vote(Transfer(BOB, "carol", 1, 0))
    replica._store.close()


def test_no_floor_until_an_epoch_starts(tmp_path):
    # The model has one floor for each epoch: `no_double_spend_views`.
    replica = open_replica(tmp_path / "1.sqlite")
    driver = driver_of(replica, prune=True)
    run(replica, transfer(0))
    take(driver, attested(replica))
    assert table_rows(tmp_path / "1.sqlite", "floors") == 0
    replica._store.close()


def test_an_epoch_applies_the_floor_when_pruning_and_only_then(tmp_path):
    for prune, floors in ((True, 1), (False, 0)):
        path = tmp_path / f"{prune}.sqlite"
        replica = open_replica(path)
        driver = driver_of(replica, prune=prune)
        run(replica, transfer(0))
        take(driver, attested(replica))
        current = replica.committee
        change = EpochChange.create(current, [m.public_key for m in NEXT], 1, GOVERNANCE, SIGNERS[:2])
        from core.attestation import EpochReport

        reports = tuple(
            sorted(
                (EpochReport.create(current, m, change.change_id, ()) for m in MEMBERS[:3]),
                key=lambda r: r.validator,
            )
        )
        driver._install(EpochClosure(change, reports))
        assert table_rows(path, "floors") == floors
        replica._store.close()


def test_votes_of_ended_epochs_go_and_those_of_this_one_stay(tmp_path):
    path = tmp_path / "1.sqlite"
    replica = open_replica(path)
    store = replica._store
    signed = signed_by(SENDER, transfer(0))
    assert store.record_vote(signed.transfer, signed)
    run(replica, transfer(0))
    snapshot = attested(replica)
    assert replica.install_snapshot(snapshot)
    next_epoch(replica)
    assert store.record_vote(transfer(1))
    assert table_rows(path, "votes") == 2
    replica.apply_floor()
    assert table_rows(path, "votes") == 1
    assert table_rows(path, "vote_evidence") == 0
    assert [e.nonce for e in store.votes()] == [1]
    store.close()


# --- The driver: asking, collecting, serving ------------------------------------------------------


class Drivers:
    def __init__(self, tmp_path, **settings):
        self.drivers = [
            driver_of(open_replica(tmp_path / f"{i}.sqlite", i), **settings) for i in range(4)
        ]

    def all_run(self, *events, indexes=(0, 1, 2, 3)):
        for index in indexes:
            run(self.drivers[index].replica, *events)

    def exchange(self, proposer, output, indexes=(1, 2, 3)):
        """A request reaches `indexes`, their votes come back. Returns the last output."""
        final = None
        for message in output.broadcasts:
            if message["type"] != "SNAPSHOT_REQUEST":
                continue
            for index in indexes:
                for reply in self.drivers[index].handle_message(wire(message)).replies:
                    answer = self.drivers[proposer].handle_message(wire(reply))
                    if answer.broadcasts:
                        final = answer
        return final


def test_a_proposer_gets_a_quorum_and_sends_the_snapshot(tmp_path):
    cluster = Drivers(tmp_path)
    cluster.all_run(transfer(0))
    proposer = cluster.drivers[0]
    final = cluster.exchange(0, proposer.propose_snapshot())
    assert final is not None
    assert final.broadcasts[0]["type"] == "SNAPSHOT"
    assert proposer.replica.base is not None
    snapshot = decode_snapshot(wire(final.broadcasts[0]))
    assert snapshot.verify(COMMITTEE)
    assert len(snapshot.attestations) == 3


def test_a_vote_for_another_digest_does_not_count(tmp_path):
    cluster = Drivers(tmp_path)
    cluster.all_run(transfer(0))
    proposer = cluster.drivers[0]
    proposer.propose_snapshot()
    other = "ab" * 32
    attestation = SnapshotAttestation.create(COMMITTEE, MEMBERS[1], other, ())
    proposer.handle_message(wire(encode_snapshot_vote(other, attestation)))
    assert list(proposer._snapshot_votes) == [0]


def test_a_vote_with_a_bad_signature_does_not_count(tmp_path):
    cluster = Drivers(tmp_path)
    cluster.all_run(transfer(0))
    proposer = cluster.drivers[0]
    proposer.propose_snapshot()
    digest = proposer._snapshot.digest
    bad = SnapshotAttestation(1, (), b"\0" * 64)
    proposer.handle_message(wire(encode_snapshot_vote(digest, bad)))
    assert list(proposer._snapshot_votes) == [0]


def test_a_vote_with_nothing_asked_does_nothing(tmp_path):
    cluster = Drivers(tmp_path)
    attestation = SnapshotAttestation.create(COMMITTEE, MEMBERS[1], "ab" * 32, ())
    output = cluster.drivers[0].handle_message(wire(encode_snapshot_vote("ab" * 32, attestation)))
    assert not output.broadcasts


def test_one_member_voting_twice_does_not_make_a_quorum(tmp_path):
    cluster = Drivers(tmp_path)
    cluster.all_run(transfer(0))
    proposer = cluster.drivers[0]
    output = proposer.propose_snapshot()
    message = output.broadcasts[0]
    reply = cluster.drivers[1].handle_message(wire(message)).replies[0]
    proposer.handle_message(wire(reply))
    proposer.handle_message(wire(reply))
    assert proposer.replica.base is None


def test_a_member_behind_is_asked_again_and_then_signs(tmp_path):
    cluster = Drivers(tmp_path, snapshot_every=1)
    clock = [0.0]
    proposer = cluster.drivers[0]
    proposer._clock = lambda: clock[0]
    cluster.all_run(transfer(0), indexes=(0, 1))
    first = proposer.propose_snapshot()
    assert cluster.exchange(0, first) is None
    assert proposer.replica.base is None
    run(cluster.drivers[2].replica, transfer(0))
    clock[0] += 5
    again = proposer.retry()
    assert again.broadcasts[0]["digest"] == first.broadcasts[0]["digest"]
    assert cluster.exchange(0, again) is not None
    assert proposer.replica.base is not None


def test_after_a_while_a_new_snapshot_is_asked_for(tmp_path):
    cluster = Drivers(tmp_path, snapshot_every=1)
    clock = [0.0]
    proposer = cluster.drivers[0]
    proposer._clock = lambda: clock[0]
    cluster.all_run(transfer(0), indexes=(0,))
    first = proposer.propose_snapshot()
    run(proposer.replica, transfer(1))
    clock[0] += QuorumDriver.SNAPSHOT_ASK_SECONDS + 1
    later = proposer.retry()
    assert later.broadcasts[0]["digest"] != first.broadcasts[0]["digest"]


def test_nothing_is_due_with_few_events_or_with_the_setting_off(tmp_path):
    cluster = Drivers(tmp_path, snapshot_every=5)
    cluster.all_run(transfer(0))
    assert not cluster.drivers[0].retry().broadcasts

    plain = Drivers(tmp_path / "x" if (tmp_path / "x").mkdir() is None else None)
    plain.all_run(*[transfer(n) for n in range(5)])
    assert not plain.drivers[0].retry().broadcasts


def test_members_start_at_different_points(tmp_path):
    cluster = Drivers(tmp_path, snapshot_every=4)
    cluster.all_run(*[transfer(n) for n in range(4)])
    assert cluster.drivers[0].retry().broadcasts
    assert not cluster.drivers[3].retry().broadcasts
    cluster.all_run(*[transfer(n) for n in range(4, 8)])
    assert cluster.drivers[3].retry().broadcasts


def test_a_halted_node_asks_for_nothing(tmp_path):
    cluster = Drivers(tmp_path, snapshot_every=1)
    cluster.all_run(transfer(0))
    driver = cluster.drivers[0]
    driver.replica.record_halt(
        certificate(transfer(1, receiver="x")),
        certificate(transfer(1, receiver="y")),
    )
    assert not driver.retry().broadcasts


def test_a_node_that_halts_stops_asking_for_what_it_was_asking(tmp_path):
    cluster = Drivers(tmp_path, snapshot_every=1)
    cluster.all_run(transfer(0))
    driver = cluster.drivers[0]
    assert driver.propose_snapshot().broadcasts
    driver.replica.record_halt(
        certificate(transfer(1, receiver="x")),
        certificate(transfer(1, receiver="y")),
    )
    assert not driver.retry().broadcasts


def test_an_ended_committee_gets_a_new_signature_when_pruning(tmp_path):
    # Otherwise a node with nothing to catch up on could serve only a snapshot nobody may take.
    cluster = Drivers(tmp_path, snapshot_every=1000, prune=True)
    driver = cluster.drivers[0]
    run(driver.replica, transfer(0))
    take(driver, attested(driver.replica))
    assert not driver._snapshot_is_due()
    next_epoch(driver.replica)
    # Not a member any more, so it does not ask. A member does.
    assert not driver._snapshot_is_due()
    other = cluster.drivers[1]
    run(other.replica, transfer(0))
    take(other, attested(other.replica))
    current = other.replica.committee
    change = EpochChange.create(
        current,
        [m.public_key for m in MEMBERS],
        1,
        GOVERNANCE,
        SIGNERS[:2],
    )
    from core.attestation import EpochReport

    reports = tuple(
        sorted(
            (EpochReport.create(current, m, change.change_id, ()) for m in MEMBERS[:3]),
            key=lambda r: r.validator,
        )
    )
    other.replica.install_closure(EpochClosure(change, reports))
    assert other._snapshot_is_due()


def request_to(driver, frontier):
    from network.message import encode_certificate_sync_request

    return driver.handle_message(wire(encode_certificate_sync_request(frontier)))


def types_of(output):
    return [message["type"] for message in output.replies]


def test_a_peer_behind_a_pruned_node_gets_the_snapshot_then_the_rest(tmp_path):
    server = driver_of(open_replica(tmp_path / "1.sqlite"), prune=True)
    run(server.replica, transfer(0), transfer(1))
    take(server, attested(server.replica))
    run(server.replica, transfer(2))
    behind = driver_of(open_replica(tmp_path / "2.sqlite", 1))

    output = request_to(server, behind._frontier())
    assert types_of(output) == ["SNAPSHOT", "CERTIFICATE_SYNC"]
    for message in output.replies:
        behind.handle_message(wire(message))
    assert behind.replica.state.root() == server.replica.state.root()


def test_what_was_pruned_is_not_served_from_an_old_index(tmp_path):
    server = driver_of(open_replica(tmp_path / "1.sqlite"), prune=True)
    run(server.replica, transfer(0))
    assert types_of(request_to(server, {})) == ["CERTIFICATE_SYNC"]
    take(server, attested(server.replica))
    assert types_of(request_to(server, {})) == ["SNAPSHOT"]


def test_a_peer_that_is_not_behind_does_not_get_it_again(tmp_path):
    server = driver_of(open_replica(tmp_path / "1.sqlite"), prune=True)
    run(server.replica, transfer(0))
    snapshot = attested(server.replica)
    take(server, snapshot)
    peer = driver_of(open_replica(tmp_path / "2.sqlite", 1))
    take(peer, snapshot)
    assert types_of(request_to(server, peer._frontier())) == []


def test_a_node_that_has_not_pruned_serves_the_events(tmp_path):
    server = driver_of(open_replica(tmp_path / "1.sqlite"))
    run(server.replica, transfer(0))
    take(server, attested(server.replica))
    assert types_of(request_to(server, {})) == ["CERTIFICATE_SYNC"]


def test_a_node_with_holes_does_not_pretend_to_have_what_it_lacks(tmp_path):
    # It took a snapshot past nonces it never ran, so its log for that sender starts later.
    server = driver_of(open_replica(tmp_path / "1.sqlite"))
    ahead = open_replica(tmp_path / "2.sqlite", 1)
    bob_pays = Transfer(BOB, "carol", 1, 0)
    run(ahead, transfer(0, 5))
    run(server.replica, transfer(0, 5), bob_pays)
    take(server, attested(ahead))
    run(ahead, transfer(1), bob_pays)
    next_alice = attested(ahead)
    take(server, next_alice)
    output = request_to(server, {BOB: 0})
    assert "SNAPSHOT" in types_of(output)
    certificates = [
        item
        for message in output.replies
        if message["type"] == "CERTIFICATE_SYNC"
        for item in message["certificates"]
    ]
    assert all(item["transfer"]["nonce"] == 0 for item in certificates)


def test_a_frontier_with_a_gap_asks_from_the_right_nonce(tmp_path):
    server = driver_of(open_replica(tmp_path / "1.sqlite"), prune=True)
    run(server.replica, transfer(0), transfer(1))
    take(server, attested(server.replica))
    run(server.replica, transfer(2), transfer(3))
    output = request_to(server, {ALICE: 3})
    [message] = output.replies
    assert [item["transfer"]["nonce"] for item in message["certificates"]] == [3]


def test_a_node_asks_with_what_the_snapshot_gave_it(tmp_path):
    server = driver_of(open_replica(tmp_path / "1.sqlite"))
    run(server.replica, transfer(0))
    peer = driver_of(open_replica(tmp_path / "2.sqlite", 1))
    assert peer._frontier() == {}
    take(peer, attested(server.replica))
    assert peer._frontier() == {ALICE: 1}


def test_a_snapshot_on_the_wire_that_is_nothing_new_gets_no_answer(tmp_path):
    server = open_replica(tmp_path / "1.sqlite")
    run(server, transfer(0))
    peer = driver_of(open_replica(tmp_path / "2.sqlite", 1))
    snapshot = attested(server)
    assert take(peer, snapshot).replies
    assert not take(peer, snapshot).replies


# --- Four real nodes ------------------------------------------------------------------------------


def wait_until(condition, seconds=30.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return condition()


def real_node(tmp_path, index, tag, create=True, prune=True):
    return Node(
        f"s{index}-{tag}",
        GENESIS,
        quorum=QuorumConfig(
            COMMITTEE,
            MEMBERS[index],
            tmp_path / f"{index}.sqlite",
            create=create,
            sync_interval=0.2,
            governance=GOVERNANCE,
            snapshot_every=5,
            prune=prune,
        ),
    )


def connect(left, right):
    host, port = right.address()
    assert left.connect_peer(Peer(node_id=right.node_id, host=host, port=port))


def test_real_nodes_prune_and_one_that_was_away_catches_up(tmp_path):
    tag = tmp_path.name[-8:].replace("_", "-")
    nodes = [real_node(tmp_path, index, tag) for index in range(3)]

    for node in nodes:
        node.start()

    late = None

    try:
        connect(nodes[0], nodes[1])
        connect(nodes[0], nodes[2])
        connect(nodes[1], nodes[2])
        events = [signed_by(SENDER, transfer(n)) for n in range(12)]

        for event in events:
            assert nodes[0].submit(event)
            assert wait_until(lambda: all(n.state.nonce(ALICE) > event.transfer.nonce for n in nodes))

        assert wait_until(lambda: all(n._quorum.replica.base is not None for n in nodes))
        assert wait_until(
            lambda: all(certificate_rows(tmp_path / f"{i}.sqlite") < 12 for i in range(3))
        )

        late = real_node(tmp_path, 3, tag)
        late.start()
        connect(nodes[0], late)
        connect(nodes[1], late)
        assert wait_until(lambda: late.state.root() == nodes[0].state.root())
        assert late._quorum.replica.base is not None
        assert len(late.local_events) < 12

        # And it goes on: a new event from the node that was away.
        assert late.submit(signed_by(SENDER, transfer(12)))
        assert wait_until(lambda: all(n.state.nonce(ALICE) == 13 for n in (*nodes, late)))
        assert len({n.state.root() for n in (*nodes, late)}) == 1
    finally:
        for node in (*nodes, *( [late] if late else [])):
            node.stop()

    # A restart of a node that pruned, from its own file.
    again = real_node(tmp_path, 0, tag, create=False)
    assert again.state.nonce(ALICE) == 13
    again.stop()
