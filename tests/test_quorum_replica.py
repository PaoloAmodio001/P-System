"""QuorumReplica: what the differential test against runNode cannot see.

The rules themselves are compared with the Lean model in
tests/test_quorum_differential.py. Here: the order of the durable steps, the
restart, and the checks made when a replica starts.
"""

import pytest

import network.quorum.replica
from core.attestation import Committee, QuorumCertificate, Vote, vote_payload
from core.derive import StateDeriver
from core.event import Transfer
from core.state import State
from crypto.identity import Identity
from network.quorum import QuorumReplica, SqliteVoteStore, VoteStoreError
from tests.test_quorum_certificate import MALFORMED_EVENTS

GENESIS = State({"alice": 10})
A = Transfer("alice", "bob", 8, 0)
B = Transfer("alice", "carol", 8, 0)
NEXT = Transfer("alice", "bob", 1, 1, (A.event_id(),))


@pytest.fixture
def members():
    identities = [Identity.create() for _ in range(4)]
    identities.sort(key=lambda identity: identity.public_key)
    return identities


@pytest.fixture
def committee(members):
    return Committee.create([m.public_key for m in members], 1, GENESIS)


def accept(_event) -> bool:
    return True


def open_replica(path, members, committee, create=True, auth=accept, index=0):
    identity = members[index]
    store = SqliteVoteStore(path, committee, identity.public_key, create=create)
    return QuorumReplica(identity, GENESIS, store, auth)


def certificate(committee, members, event, *indexes):
    return QuorumCertificate(
        event,
        tuple(Vote.create(committee, members[i], event) for i in indexes),
    )


@pytest.fixture
def path(tmp_path):
    return tmp_path / "votes.sqlite"


# --- Starting ------------------------------------------------------------


def test_replica_refuses_another_genesis(path, members, committee):
    store = SqliteVoteStore(path, committee, members[0].public_key, create=True)
    with pytest.raises(ValueError):
        QuorumReplica(members[0], State({"alice": 11}), store, accept)


def test_replica_refuses_a_store_of_another_validator(path, members, committee):
    store = SqliteVoteStore(path, committee, members[0].public_key, create=True)
    with pytest.raises(ValueError):
        QuorumReplica(members[1], GENESIS, store, accept)


def test_replica_does_not_share_the_initial_state(path, members, committee):
    initial = GENESIS.copy()
    store = SqliteVoteStore(path, committee, members[0].public_key, create=True)
    replica = QuorumReplica(members[0], initial, store, accept)
    assert replica.handle_certificate(certificate(committee, members, A, 0, 1, 2, 3))
    assert initial.balance("alice") == 10


# --- A vote is signed only after it is recorded --------------------------


def test_returned_vote_verifies(path, members, committee):
    replica = open_replica(path, members, committee)
    vote = replica.handle_vote_request(A)
    assert vote.validator == 0
    assert vote.verify(committee, A)


def test_voting_again_gives_the_same_signature(path, members, committee):
    # Signatures are not stored: this relies on Ed25519 being deterministic.
    replica = open_replica(path, members, committee)
    assert replica.handle_vote_request(A) == replica.handle_vote_request(A)


def test_voting_again_after_a_restart_gives_the_same_signature(path, members, committee):
    first = open_replica(path, members, committee)
    vote = first.handle_vote_request(A)
    first._store.close()
    second = open_replica(path, members, committee, create=False)
    assert second.handle_vote_request(A) == vote


def test_refused_vote_gives_no_signature(path, members, committee, monkeypatch):
    replica = open_replica(path, members, committee)
    assert replica.handle_vote_request(A) is not None

    def fail(*_):
        raise AssertionError("signed a refused vote")

    monkeypatch.setattr(network.quorum.replica.Vote, "create", fail)
    assert replica.handle_vote_request(B) is None


def test_refused_by_auth_gives_no_signature_and_takes_no_lock(path, members, committee):
    replica = open_replica(
        path, members, committee, auth=lambda e: e.event_id() != B.event_id()
    )
    assert replica.handle_vote_request(B) is None
    assert replica.votes() == []
    assert replica.handle_vote_request(A) is not None


def test_failed_write_gives_no_signature(path, members, committee, monkeypatch):
    replica = open_replica(path, members, committee)
    signed = []
    monkeypatch.setattr(
        network.quorum.replica.Vote, "create", lambda *args: signed.append(args)
    )

    def fail(_event, _signed=None, _gathering=False, _round_state=None):
        raise VoteStoreError("disk full")

    monkeypatch.setattr(replica._store, "record_vote", fail)
    with pytest.raises(VoteStoreError):
        replica.handle_vote_request(A)
    assert signed == []


def test_vote_is_on_disk_when_it_is_signed(path, members, committee, monkeypatch):
    # Read through a second connection: uncommitted data would not be visible.
    replica = open_replica(path, members, committee)
    other = SqliteVoteStore(path, committee, members[0].public_key)
    seen = []
    original = Vote.create

    def checking(*args):
        seen.append([event.canonical() for event in other.votes()])
        return original(*args)

    monkeypatch.setattr(network.quorum.replica.Vote, "create", checking)
    replica.handle_vote_request(A)
    other.close()
    assert seen == [[A.canonical()]]


# --- Execution -----------------------------------------------------------


def test_failed_write_leaves_the_state_unchanged(path, members, committee, monkeypatch):
    replica = open_replica(path, members, committee)

    def fail(_certificate):
        raise VoteStoreError("disk full")

    monkeypatch.setattr(replica._store, "append_certificate", fail)
    with pytest.raises(VoteStoreError):
        replica.handle_certificate(certificate(committee, members, A, 0, 1, 2, 3))
    assert replica.executed == []
    assert replica.state.balance("alice") == 10
    assert replica.state.nonce("alice") == 0


def test_signatures_are_not_checked_for_what_cannot_run(path, members, committee, monkeypatch):
    # They are the expensive check, so a certificate that cannot run costs none.
    replica = open_replica(path, members, committee)

    def fail(*_):
        raise AssertionError("signatures checked")

    monkeypatch.setattr(QuorumCertificate, "verify", fail)
    ahead = QuorumCertificate(Transfer("alice", "bob", 1, 5), ())
    assert not replica.handle_certificate(ahead)


def test_state_is_what_the_deriver_computes(path, members, committee):
    # state_is_derive in the model, here for the real StateDeriver.
    replica = open_replica(path, members, committee)
    assert replica.handle_certificate(certificate(committee, members, A, 0, 1, 2, 3))
    assert replica.handle_certificate(certificate(committee, members, NEXT, 0, 1, 2, 3))
    derived = StateDeriver.apply_events(GENESIS, replica.executed)
    assert derived.root() == replica.state.root()


# --- Restart -------------------------------------------------------------


def test_restart_restores_state_log_and_votes(path, members, committee):
    first = open_replica(path, members, committee)
    assert first.handle_vote_request(B) is not None
    # A valid certificate overrides this validator's own vote.
    assert first.handle_certificate(certificate(committee, members, A, 0, 1, 2, 3))
    assert first.handle_certificate(certificate(committee, members, NEXT, 0, 1, 2, 3))
    root = first.state.root()
    log = list(first.log)
    first._store.close()

    second = open_replica(path, members, committee, create=False)
    assert second.state.root() == root
    assert second.log == log
    assert second.handle_vote_request(A) is None
    assert not second.handle_certificate(log[0])


def test_restart_with_lost_log_keeps_the_lock(path, members, committee):
    # In the model votes and log are independent: this is a valid shorter run.
    first = open_replica(path, members, committee)
    assert first.handle_vote_request(A) is not None
    assert first.handle_certificate(certificate(committee, members, A, 0, 1, 2, 3))
    first._store._connection.execute("DELETE FROM certificates")
    first._store.close()

    second = open_replica(path, members, committee, create=False)
    assert second.executed == []
    assert second.handle_vote_request(B) is None
    assert second.handle_certificate(certificate(committee, members, A, 0, 1, 2, 3))


def test_tampered_log_does_not_start(path, members, committee):
    first = open_replica(path, members, committee)
    assert first.handle_certificate(certificate(committee, members, A, 0, 1, 2, 3))
    first._store._connection.execute(
        "UPDATE certificates SET signatures = '[]'"
    )
    first._store.close()

    store = SqliteVoteStore(path, committee, members[0].public_key)
    with pytest.raises(VoteStoreError):
        QuorumReplica(members[0], GENESIS, store, accept)


class SameIdTransfer(Transfer):
    def event_id(self) -> str:
        return "f" * 64


def test_signature_on_one_event_is_not_valid_for_another_with_the_same_id(
    path, members, committee
):
    # Python signs the canonical form: a hash collision does not let a certificate
    # move to another event. The differential test compares this with the model too.
    first = SameIdTransfer("alice", "bob", 8, 0)
    second = SameIdTransfer("alice", "carol", 8, 0)
    votes = tuple(Vote.create(committee, members[i], first) for i in (0, 1, 2))
    replica = open_replica(path, members, committee)
    assert QuorumCertificate(first, votes).verify(committee)
    assert not replica.handle_certificate(QuorumCertificate(second, votes))


# --- Malformed events, which cannot be written in the Lean model -------------


@pytest.mark.parametrize("name", MALFORMED_EVENTS)
def test_malformed_vote_request_is_refused_before_auth_and_takes_no_lock(
    path, members, committee, name
):
    def auth(_event):
        raise AssertionError("auth must not see a malformed event")

    replica = open_replica(path, members, committee, auth=auth)

    assert replica.handle_vote_request(MALFORMED_EVENTS[name]) is None
    assert replica.votes() == []


def test_malformed_vote_request_does_not_block_the_valid_one(path, members, committee):
    # Same (sender, nonce) as A. Before the check this signed a negative amount.
    replica = open_replica(path, members, committee)

    assert replica.handle_vote_request(Transfer("alice", "bob", -8, 0)) is None
    assert replica.handle_vote_request(A) is not None
    assert replica.votes() == [A]


@pytest.mark.parametrize("value", [None, 1, "event", object()])
def test_vote_request_that_is_not_an_event_is_refused(path, members, committee, value):
    replica = open_replica(path, members, committee)
    assert replica.handle_vote_request(value) is None
    assert replica.votes() == []


@pytest.mark.parametrize("name", MALFORMED_EVENTS)
def test_malformed_certificate_is_refused_not_an_error(path, members, committee, name):
    replica = open_replica(path, members, committee)
    before = replica.state.root()

    assert replica.handle_certificate(QuorumCertificate(MALFORMED_EVENTS[name], ())) is False
    assert replica.state.root() == before
    assert replica.log == []


@pytest.mark.parametrize("value", [None, 1, "event", object()])
def test_certificate_on_what_is_not_an_event_is_refused(path, members, committee, value):
    replica = open_replica(path, members, committee)
    assert replica.handle_certificate(QuorumCertificate(value, ())) is False


def test_certificate_with_a_bool_amount_and_real_signatures_is_not_executed(
    path, members, committee
):
    # `True` passes every check on the amount: it is an int greater than zero.
    event = Transfer("alice", "bob", True, 0)
    payload = vote_payload(committee, event)
    forged = QuorumCertificate(
        event,
        tuple(Vote(i, members[i].sign(payload)) for i in range(committee.quorum)),
    )
    replica = open_replica(path, members, committee)

    assert replica.handle_certificate(forged) is False
    assert replica.log == []
    assert replica.state.nonce("alice") == 0


# --- A halted node --------------------------------------------------------


def _halt_replica(replica, committee, members):
    replica._store.record_halt(
        certificate(committee, members, A, 0, 1, 2, 3),
        certificate(committee, members, B, 0, 1, 2, 3),
    )


def test_halted_replica_gives_no_signature(path, members, committee):
    replica = open_replica(path, members, committee)
    assert replica.handle_vote_request(A) is not None

    _halt_replica(replica, committee, members)

    assert replica.handle_vote_request(A) is None
    assert replica.handle_vote_request(Transfer("alice", "bob", 1, 5)) is None


def test_halted_replica_executes_nothing_and_keeps_its_state(path, members, committee):
    replica = open_replica(path, members, committee)
    before = replica.state.root()
    _halt_replica(replica, committee, members)

    assert not replica.handle_certificate(certificate(committee, members, A, 0, 1, 2, 3))

    assert replica.state.root() == before
    assert replica.log == []


def test_halt_survives_a_restart_with_the_log_replayed(path, members, committee):
    replica = open_replica(path, members, committee)
    assert replica.handle_certificate(certificate(committee, members, A, 0, 1, 2, 3))
    root = replica.state.root()
    _halt_replica(replica, committee, members)
    replica._store.close()

    again = open_replica(path, members, committee, create=False)

    assert again.state.root() == root
    assert [event.canonical() for event in again.executed] == [A.canonical()]
    assert again.handle_vote_request(NEXT) is None
    assert not again.handle_certificate(certificate(committee, members, NEXT, 0, 1, 2, 3))
    assert again.state.root() == root
