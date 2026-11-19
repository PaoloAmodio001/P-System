import pytest
"""Observability for permanently locked nonces (priority 2)."""

import json
import logging

from core.attestation import EpochChange, EpochReport, Governance
from core.event import Transfer
from core.signed_event import SignedTransfer
from core.state import State
from crypto.identity import Identity
from network.message import encode_epoch_change, encode_vote_request
from network.quorum import QuorumDriver, QuorumReplica, SqliteVoteStore
from core.attestation import Committee

from network.quorum import QuorumDriver as _Driver


@pytest.fixture(autouse=True)
def _close_at_once(monkeypatch):
    # Closures here form at once, with what is open locked: the limit that remains when the wait
    # for decisions runs out (`QuorumDriver.CLOSING_GRACE_SECONDS`).
    monkeypatch.setattr(_Driver, "CLOSING_GRACE_SECONDS", 0.0)


SENDER = Identity.create()
ALICE = SENDER.identity_id
GENESIS = State({ALICE: 100})
SIGNERS = [Identity.create() for _ in range(3)]
GOVERNANCE = Governance(tuple(sorted(s.public_key for s in SIGNERS)), 2)
MEMBERS = sorted((Identity.create() for _ in range(4)), key=lambda m: m.public_key)
STANDARD = Committee.create([m.public_key for m in MEMBERS], 1, GENESIS)


def wire(message):
    return json.loads(json.dumps(message))


def spend(nonce, receiver="bob"):
    return SignedTransfer.create(SENDER, Transfer(ALICE, receiver, 1, nonce))


class Cluster:
    def __init__(self, tmp_path):
        self.drivers = []
        for index, member in enumerate(MEMBERS):
            store = SqliteVoteStore(
                tmp_path / f"{index}.sqlite",
                STANDARD,
                member.public_key,
                create=True,
                governance=GOVERNANCE,
            )
            replica = QuorumReplica(member, GENESIS, store, lambda _event: True)
            self.drivers.append(QuorumDriver(replica, GOVERNANCE))

    def votes_for(self, signed, indexes):
        for index in indexes:
            self.drivers[index].handle_message(wire(encode_vote_request(signed)))

    def close(self, reporters):
        current = self.drivers[0].committee
        change = EpochChange.create(
            current,
            [m.public_key for m in MEMBERS],
            current.f,
            GOVERNANCE,
            SIGNERS[:2],
        )
        collector = self.drivers[reporters[0]]
        collector.propose_epoch_change(change)
        closure = None
        for index in reporters[1:]:
            for reply in self.drivers[index].handle_message(wire(encode_epoch_change(change))).replies:
                for message in collector.handle_message(wire(reply)).broadcasts:
                    if message.get("type") == "EPOCH_CLOSURE":
                        closure = message
        assert closure is not None
        for index, driver in enumerate(self.drivers):
            if index != reporters[0]:
                driver.handle_message(wire(closure))
        return closure

    def vote_is_given(self, index, signed):
        return bool(self.drivers[index].handle_message(wire(encode_vote_request(signed))).replies)


def test_split_votes_log_permanently_locked_nonce_and_prevent_reuse(tmp_path, caplog):
    cluster = Cluster(tmp_path)
    first, second = spend(0, "first"), spend(0, "second")
    cluster.votes_for(first, [0])
    cluster.votes_for(second, [1])

    with caplog.at_level(logging.ERROR, logger="psystem.quorum"):
        cluster.close([0, 1, 2])

    records = [r for r in caplog.records if r.message == "nonce.locked_permanently"]
    assert records, "expected nonce.locked_permanently log"
    rec = records[0]
    assert rec.levelno >= logging.WARNING
    assert rec.sender == ALICE
    assert rec.nonce == 0
    assert rec.epoch == 0
    assert rec.reason == "split_votes_no_unlock"
    assert rec.divergent_votes >= 2
    assert isinstance(rec.versions, int) and rec.versions >= 2
    assert "signature" not in str(getattr(rec, "__dict__", {})).lower()

    assert cluster.drivers[0].replica.nonce_locked_permanently_total >= 1

    # non-reusable: locked for good in standard mode
    third = spend(0, "third")
    assert not any(cluster.vote_is_given(index, third) for index in range(4))
