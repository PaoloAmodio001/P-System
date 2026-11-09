"""GET /v1/certificates/{id} finds a certificate by id, without scanning the log under the lock of the node.

Before, the API computed the id of every certificate in the log, holding `Node._state_lock`: with a long log one
client could keep the node from handling messages. The replica now keeps an index by id, updated with the log:
on execution, at a restart, and when pruning drops what a snapshot covers.
"""

import json
import urllib.error
import urllib.request

import pytest

from core.attestation import Committee, QuorumCertificate, Snapshot, SnapshotAttestation, Vote
from core.event import Transfer
from core.state import State
from crypto.identity import Identity
from network.quorum import QuorumReplica, SqliteVoteStore

SENDER = Identity.create()
ALICE = SENDER.identity_id
GENESIS = State({ALICE: 1000})
MEMBERS = sorted((Identity.create() for _ in range(4)), key=lambda m: m.public_key)
COMMITTEE = Committee.create([m.public_key for m in MEMBERS], 1, GENESIS)


def certificate(nonce: int) -> QuorumCertificate:
    event = Transfer(ALICE, "bob", 1, nonce)
    return QuorumCertificate(event, tuple(Vote.create(COMMITTEE, m, event) for m in MEMBERS[:3]), 0)


def open_replica(path, create=True) -> QuorumReplica:
    store = SqliteVoteStore(path, COMMITTEE, MEMBERS[0].public_key, create=create)
    return QuorumReplica(MEMBERS[0], GENESIS, store, lambda _event: True)


def test_a_lookup_computes_no_id(tmp_path, monkeypatch):
    replica = open_replica(tmp_path / "v.sqlite")
    made = [certificate(n) for n in range(50)]
    for one in made:
        assert replica.handle_certificate(one)
    wanted = made[-1].event.event_id()
    calls = []
    original = Transfer.event_id
    monkeypatch.setattr(Transfer, "event_id", lambda self: calls.append(1) or original(self))

    assert replica.certificate_of(wanted) == made[-1]
    assert replica.certificate_of("ab" * 32) is None
    assert calls == []


def test_the_index_survives_a_restart(tmp_path):
    path = tmp_path / "v.sqlite"
    replica = open_replica(path)
    one = certificate(0)
    assert replica.handle_certificate(one)
    replica._store.close()

    again = open_replica(path, create=False)

    assert again.certificate_of(one.event.event_id()) == one


def test_what_pruning_drops_is_no_longer_found(tmp_path):
    replica = open_replica(tmp_path / "v.sqlite")
    first, second = certificate(0), certificate(1)
    assert replica.handle_certificate(first)
    candidate = replica.candidate_snapshot()
    snapshot = Snapshot(
        candidate.epoch,
        candidate.state,
        candidate.ids,
        tuple(SnapshotAttestation.create(COMMITTEE, m, candidate.digest, ()) for m in MEMBERS[:3]),
    )
    assert replica.install_snapshot(snapshot)
    assert replica.handle_certificate(second)
    replica.prune_covered()

    assert replica.certificate_of(first.event.event_id()) is None
    assert replica.certificate_of(second.event.event_id()) == second


def test_a_certificate_under_a_snapshot_kept_on_file_is_found_after_a_restart(tmp_path):
    # Without pruning, a restart reads back what the snapshot covers by another path than execution.
    path = tmp_path / "v.sqlite"
    replica = open_replica(path)
    first = certificate(0)
    assert replica.handle_certificate(first)
    candidate = replica.candidate_snapshot()
    snapshot = Snapshot(
        candidate.epoch,
        candidate.state,
        candidate.ids,
        tuple(SnapshotAttestation.create(COMMITTEE, m, candidate.digest, ()) for m in MEMBERS[:3]),
    )
    assert replica.install_snapshot(snapshot)
    replica._store.close()

    again = open_replica(path, create=False)

    assert again.is_covered(first.event)
    assert again.certificate_of(first.event.event_id()) == first


def test_the_api_answers_from_the_index(tmp_path, monkeypatch):
    from network.deployment import read_node_config, write_genesis
    from network.node_tls_identity import create_authority, issue_node_certificate
    from network.service import Service
    from tests.test_service import url, write_config

    authority = create_authority(tmp_path / "ca")
    issue_node_certificate(authority, "api-node", tmp_path)
    members = []
    for i in range(4):
        member = Identity.create()
        member.save(tmp_path / f"m{i}.key")
        members.append(member)
    write_genesis(tmp_path / "genesis.json", [m.public_key for m in members], 1, {})
    running = Service(read_node_config(write_config(tmp_path)), create=True)
    running.start()
    asked = []
    replica = running.node._quorum.replica
    monkeypatch.setattr(replica, "certificate_of", lambda event_id: asked.append(event_id))

    try:
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(url(running) + "/v1/certificates/" + "cd" * 32, timeout=5)

        assert error.value.code == 404
        assert json.loads(error.value.read())["error"] == "NOT EXECUTED HERE"
        assert asked == ["cd" * 32]
    finally:
        running.stop()
