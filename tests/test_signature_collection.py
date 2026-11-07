"""Signature collection idempotency, outside-committee rejection, and timeout (priority 3)."""

import json
import logging

import pytest

from core.attestation import Committee, QuorumCertificate, Vote
from core.event import Transfer
from core.signed_event import SignedTransfer
from core.state import State
from crypto.identity import Identity
from network.message import decode_vote, encode_vote, encode_vote_request
from network.quorum import QuorumDriver, QuorumReplica, SqliteVoteStore

SENDER = Identity.create()
PAYER = SENDER.identity_id
GENESIS = State({PAYER: 10})
A = Transfer(PAYER, "bob", 1, 0)


def signed(event=A):
    return SignedTransfer.create(SENDER, event)


class Cluster:
    def __init__(self, path, clock=None):
        self.members = sorted(
            (Identity.create() for _ in range(4)),
            key=lambda i: i.public_key,
        )
        self.committee = Committee.create([m.public_key for m in self.members], 1, GENESIS)
        store = SqliteVoteStore(path, self.committee, self.members[0].public_key, create=True)
        self.store = store
        kwargs = {}
        if clock is not None:
            kwargs["clock"] = clock
        self.driver = QuorumDriver(
            QuorumReplica(self.members[0], GENESIS, store, lambda _: True),
            **kwargs,
        )

    def close(self):
        self.store.close()

    def vote_message(self, event, index):
        return encode_vote(event, Vote.create(self.committee, self.members[index], event))


@pytest.fixture
def cluster(tmp_path):
    c = Cluster(tmp_path / "v.sqlite")
    yield c
    c.close()


def test_same_vote_twice_is_idempotent(cluster):
    # Start collection as node 0 (votes and asks others)
    cluster.driver.submit(signed())
    vote = cluster.vote_message(A, 1)
    cluster.driver.handle_message(json.loads(json.dumps(vote)))
    cluster.driver.handle_message(json.loads(json.dumps(vote)))
    _, votes = cluster.driver._aggregating[A.canonical()]
    assert list(votes.keys()).count(1) == 1
    assert len(votes) == 2  # node 0's own vote + validator 1 once


def test_vote_from_validator_outside_committee_is_rejected_structured(cluster, caplog):
    cluster.driver.submit(signed())
    bad = Vote(validator=99, signature=b"x" * 64)
    message = encode_vote(A, bad)
    with caplog.at_level(logging.WARNING, logger="psystem.quorum"):
        out = cluster.driver.handle_message(json.loads(json.dumps(message)))
    assert out.replies == () and out.broadcasts == ()
    records = [r for r in caplog.records if r.message == "vote.rejected"]
    assert records
    assert records[0].reason == "validator_outside_committee_epoch"
    assert records[0].validator == 99
    assert records[0].epoch == cluster.committee.epoch
    _, votes = cluster.driver._aggregating[A.canonical()]
    assert 99 not in votes


def test_collection_timeout_is_observable_and_stops_loop(tmp_path, caplog, monkeypatch):
    now = [1000.0]

    def clock():
        return now[0]

    cluster = Cluster(tmp_path / "v.sqlite", clock=clock)
    try:
        monkeypatch.setattr(QuorumDriver, "COLLECTION_TIMEOUT_SECONDS", 5.0)
        cluster.driver.submit(signed())
        assert A.canonical() in cluster.driver._aggregating
        now[0] += 10.0
        with caplog.at_level(logging.WARNING, logger="psystem.quorum"):
            cluster.driver.retry()
        records = [r for r in caplog.records if r.message == "certificate_collection_timeout"]
        assert records
        rec = records[0]
        assert rec.sender == PAYER
        assert rec.nonce == 0
        assert rec.epoch == cluster.committee.epoch
        assert A.canonical() not in cluster.driver._aggregating
        assert A.canonical() not in cluster.driver._to_resend
        # retry again - no infinite resend loop; stays empty
        caplog.clear()
        cluster.driver.retry()
        assert not [r for r in caplog.records if r.message == "certificate_collection_timeout"]
    finally:
        cluster.close()
