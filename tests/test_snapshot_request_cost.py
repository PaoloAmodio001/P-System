"""A SNAPSHOT_REQUEST costs the peer that sends it, as other requests do.

A request makes a member derive a state from its whole log. Before, a peer paid nothing, whatever the digest, and
the same request sent again was derived again: a peer with a certificate could keep a member busy at no cost.
Now the peer pays for the steps of the derivation, and a bad signature's worth when the digest is not the one the
member derives. An attestation already given is given again from memory.
"""

from core.attestation import Committee, QuorumCertificate, Snapshot, SnapshotAttestation, Vote
from core.event import Transfer
from core.state import State
from crypto.identity import Identity
from network.message import encode_snapshot_request
from network.quorum import BAD_SIGNATURE_COST, QuorumDriver, QuorumReplica, SqliteVoteStore

SENDER = Identity.create()
ALICE = SENDER.identity_id
GENESIS = State({ALICE: 1000})
MEMBERS = sorted((Identity.create() for _ in range(4)), key=lambda m: m.public_key)
COMMITTEE = Committee.create([m.public_key for m in MEMBERS], 1, GENESIS)


def certificate(nonce: int) -> QuorumCertificate:
    event = Transfer(ALICE, "bob", 1, nonce)
    return QuorumCertificate(event, tuple(Vote.create(COMMITTEE, m, event) for m in MEMBERS[:3]), 0)


def member(tmp_path, events=40) -> QuorumDriver:
    store = SqliteVoteStore(tmp_path / "v.sqlite", COMMITTEE, MEMBERS[1].public_key, create=True)
    replica = QuorumReplica(MEMBERS[1], GENESIS, store, lambda _event: True)
    for nonce in range(events):
        assert replica.handle_certificate(certificate(nonce))
    return QuorumDriver(replica)


def request(driver, digest=None):
    candidate = driver.replica.candidate_snapshot()
    return encode_snapshot_request(candidate.epoch, digest or candidate.digest, candidate.state.nonces)


def test_a_false_digest_costs_the_peer(tmp_path):
    driver = member(tmp_path)

    output = driver.handle_message(request(driver, "ab" * 32))

    assert output.replies == ()
    assert output.cost >= BAD_SIGNATURE_COST


def test_a_true_request_is_derived_once(tmp_path):
    driver = member(tmp_path)
    first = driver.handle_message(request(driver))
    steps = driver.replica.derive_steps

    for _ in range(5):
        again = driver.handle_message(request(driver))
        assert again.replies == first.replies
        assert again.cost == 0

    assert driver.replica.derive_steps == steps
    assert len(first.replies) == 1


def test_the_work_is_charged(tmp_path):
    driver = member(tmp_path, events=400)

    output = driver.handle_message(request(driver))

    assert output.replies and output.cost >= 400 // 20


def test_a_new_base_asks_again(tmp_path):
    driver = member(tmp_path, events=3)
    driver.handle_message(request(driver))
    replica = driver.replica
    candidate = replica.candidate_snapshot()
    snapshot = Snapshot(
        candidate.epoch,
        candidate.state,
        candidate.ids,
        tuple(SnapshotAttestation.create(COMMITTEE, m, candidate.digest, ()) for m in MEMBERS[:3]),
    )
    assert replica.install_snapshot(snapshot)
    steps = replica.derive_steps

    driver.handle_message(request(driver))

    assert replica.derive_steps > steps
