"""The optional configuration of decision D2: 5f+1 members, a quorum of 4f+1, unlocking at the end of an epoch.

The rule is in formal/lean/PSystem/QuorumUnlock.lean, compared with Python in
tests/test_unlock_differential.py. Here is what it does for a node, with messages passed by hand and on real
nodes: a split nonce is free in the next epoch, and a certified event never is.
"""

import json
import time

import pytest

from core.attestation import (
    Committee,
    EpochChange,
    EpochClosure,
    EpochReport,
    Governance,
    QuorumCertificate,
    Vote,
)
from core.event import Transfer
from core.signed_event import SignedTransfer
from core.state import State
from crypto.identity import Identity
from network.deployment import DeploymentError, parse_genesis, write_genesis
from network.message import encode_epoch_change, encode_vote_request
from network.node import Node
from network.peer import Peer
from network.quorum import QuorumConfig, QuorumDriver, QuorumReplica, SqliteVoteStore
from sdk.client import ChainVerifier

SENDER = Identity.create()
ALICE = SENDER.identity_id
GENESIS = State({ALICE: 100})
SIGNERS = [Identity.create() for _ in range(3)]
GOVERNANCE = Governance(tuple(sorted(s.public_key for s in SIGNERS)), 2)
MEMBERS = sorted((Identity.create() for _ in range(6)), key=lambda m: m.public_key)
COMMITTEE = Committee.create([m.public_key for m in MEMBERS], 1, GENESIS, unlock=True)
STANDARD_MEMBERS = MEMBERS[:4]
STANDARD = Committee.create([m.public_key for m in STANDARD_MEMBERS], 1, GENESIS)


def wire(message: dict) -> dict:
    return json.loads(json.dumps(message))


def spend(nonce: int, receiver: str = "bob") -> SignedTransfer:
    return SignedTransfer.create(SENDER, Transfer(ALICE, receiver, 1, nonce))


# --- The committee ----------------------------------------------------------------------------------


def test_sizes_and_quorums():
    assert COMMITTEE.n == 6
    assert COMMITTEE.quorum == 5
    assert STANDARD.quorum == 3
    keys = sorted(Identity.create().public_key for _ in range(11))
    assert Committee.create(keys, 2, GENESIS, unlock=True).quorum == 9


@pytest.mark.parametrize(
    "count,f,unlock",
    [(4, 1, True), (6, 1, False), (7, 1, True), (5, 1, True), (11, 2, False), (7, 2, True)],
)
def test_a_committee_of_another_size_is_refused(count, f, unlock):
    keys = sorted(Identity.create().public_key for _ in range(count))
    with pytest.raises(ValueError, match="COMMITTEE SIZE"):
        Committee.create(keys, f, GENESIS, unlock=unlock)


def test_the_setting_is_a_boolean():
    with pytest.raises(ValueError):
        Committee(COMMITTEE.members, 1, GENESIS.root(), unlock=1)


def test_a_standard_committee_has_the_id_it_always_had():
    import hashlib

    data = {
        "f": STANDARD.f,
        "genesis_root": STANDARD.genesis_root,
        "members": [member.hex() for member in STANDARD.members],
    }
    expected = hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert STANDARD.committee_id == expected


def test_a_next_committee_keeps_the_configuration():
    keys = sorted(Identity.create().public_key for _ in range(6))
    change = EpochChange.create(COMMITTEE, keys, 1, GOVERNANCE, SIGNERS[:2])
    assert change.next_committee(COMMITTEE).unlock
    assert change.verify(GOVERNANCE, COMMITTEE)


def test_a_next_committee_of_the_wrong_size_is_not_an_order():
    keys = sorted(Identity.create().public_key for _ in range(4))
    change = EpochChange.create(COMMITTEE, keys, 1, GOVERNANCE, SIGNERS[:2])
    assert not change.verify(GOVERNANCE, COMMITTEE)


# --- What a closure locks -------------------------------------------------------------------------------


def closure_with(reports_by_member, committee=COMMITTEE, members=MEMBERS):
    change = EpochChange.create(
        committee,
        [m.public_key for m in members],
        committee.f,
        GOVERNANCE,
        SIGNERS[:2],
    )
    return EpochClosure(
        change,
        tuple(
            EpochReport.create(committee, members[index], change.change_id, votes)
            for index, votes in sorted(reports_by_member.items())
        ),
    )


def test_three_reports_of_five_lock_and_two_do_not():
    a, b = spend(0, "a"), spend(1, "b")
    closure = closure_with({0: [a, b], 1: [a, b], 2: [a], 3: [], 4: []})
    assert closure.verify(GOVERNANCE, COMMITTEE)
    assert [e.canonical() for e in closure.locks(COMMITTEE)] == [a.transfer.canonical()]


def test_in_a_standard_committee_everything_reported_locks():
    a = spend(0, "a")
    closure = closure_with({0: [a], 1: [], 2: []}, STANDARD, STANDARD_MEMBERS)
    assert [e.canonical() for e in closure.locks(STANDARD)] == [a.transfer.canonical()]


def test_a_reporter_that_repeats_itself_counts_once():
    a = spend(0, "a")
    report = EpochReport(0, (a, a, a), b"")
    change = EpochChange("00" * 32, COMMITTEE.members, 1)
    closure = EpochClosure(change, (report, EpochReport(1, (), b"")))
    assert closure.locks(COMMITTEE) == ()


def test_two_alternatives_over_the_threshold_both_lock():
    # Neither is certified, and nobody chooses: that nonce stays locked.
    a, b = spend(0, "a"), spend(0, "b")
    closure = closure_with({0: [a, b], 1: [a, b], 2: [a, b], 3: [], 4: []})
    assert len(closure.locks(COMMITTEE)) == 2


# --- A chain, with messages passed by hand --------------------------------------------------------------


class Cluster:
    def __init__(self, tmp_path, committee=COMMITTEE, members=MEMBERS):
        self.committee = committee
        self.members = members
        self.drivers = []
        for index, member in enumerate(members):
            store = SqliteVoteStore(
                tmp_path / f"{index}.sqlite",
                committee,
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
            [m.public_key for m in self.members],
            current.f,
            GOVERNANCE,
            SIGNERS[:2],
        )
        collector = self.drivers[reporters[0]]
        output = collector.propose_epoch_change(change)
        closure = None
        for index in reporters[1:]:
            for reply in self.drivers[index].handle_message(wire(encode_epoch_change(change))).replies:
                for message in collector.handle_message(wire(reply)).broadcasts:
                    if message["type"] == "EPOCH_CLOSURE":
                        closure = message
        assert closure is not None, output
        for index, driver in enumerate(self.drivers):
            if index != reporters[0]:
                driver.handle_message(wire(closure))
        return closure

    def vote_is_given(self, index, signed) -> bool:
        return bool(self.drivers[index].handle_message(wire(encode_vote_request(signed))).replies)


@pytest.fixture
def cluster(tmp_path):
    return Cluster(tmp_path)


def test_a_split_nonce_is_free_in_the_next_epoch(cluster):
    # Two versions, with votes split so that no version can have five.
    first, second = spend(0, "first"), spend(0, "second")
    cluster.votes_for(first, [0, 1])
    cluster.votes_for(second, [2, 3])
    cluster.close([0, 1, 2, 3, 4])
    assert cluster.drivers[0].committee.epoch == 1
    third = spend(0, "third")
    assert all(cluster.vote_is_given(index, third) for index in range(6))


def test_in_a_standard_committee_the_same_split_stays_locked(tmp_path):
    cluster = Cluster(tmp_path, STANDARD, STANDARD_MEMBERS)
    first, second = spend(0, "first"), spend(0, "second")
    cluster.votes_for(first, [0])
    cluster.votes_for(second, [1])
    cluster.close([0, 1, 2])
    third = spend(0, "third")
    assert not any(cluster.vote_is_given(index, third) for index in range(4))


def test_a_certified_event_stays_locked_whoever_reports(cluster):
    # Five signers, and any five reporters: at least three honest ones hold it.
    signed = spend(0, "certified")
    cluster.votes_for(signed, [0, 1, 2, 3, 4])
    cluster.close([1, 2, 3, 4, 5])
    other = spend(0, "other")
    assert not any(cluster.vote_is_given(index, other) for index in range(6))
    assert cluster.vote_is_given(0, signed)


def test_a_lock_stays_in_every_later_epoch(cluster):
    # `forgetting_old_locks_fails`: nobody votes for it again, so its reports are gone by then.
    signed = spend(0, "certified")
    cluster.votes_for(signed, [0, 1, 2, 3, 4])
    cluster.close([0, 1, 2, 3, 4])
    cluster.close([0, 1, 2, 3, 4])
    assert cluster.drivers[0].committee.epoch == 2
    assert not cluster.vote_is_given(0, spend(0, "other"))


def test_an_event_over_the_threshold_with_no_certificate_stays_locked(cluster):
    # Three reporters voted for it: it could have five signatures, for all a closure knows.
    signed = spend(0, "maybe")
    cluster.votes_for(signed, [0, 1, 2])
    cluster.close([0, 1, 2, 3, 4])
    assert not cluster.vote_is_given(4, spend(0, "other"))
    assert cluster.vote_is_given(4, signed)


def test_a_nonce_freed_can_be_certified_and_run(cluster):
    first, second = spend(0, "first"), spend(0, "second")
    cluster.votes_for(first, [0, 1])
    cluster.votes_for(second, [2, 3])
    cluster.close([0, 1, 2, 3, 4])
    third = spend(0, "third")
    committee = cluster.drivers[0].committee
    votes = tuple(Vote.create(committee, member, third.transfer) for member in MEMBERS[:5])
    certificate = QuorumCertificate(third.transfer, votes, committee.epoch)
    assert cluster.drivers[0].replica.handle_certificate(certificate)
    assert cluster.drivers[0].replica.state.balance("third") == 1


def test_a_certificate_needs_five_signatures(cluster):
    signed = spend(0).transfer
    votes = tuple(Vote.create(COMMITTEE, member, signed) for member in MEMBERS[:4])
    assert not QuorumCertificate(signed, votes).verify(COMMITTEE)


def test_a_client_follows_the_same_locks(cluster):
    signed = spend(0, "certified")
    cluster.votes_for(signed, [0, 1, 2, 3, 4])
    closure = cluster.close([0, 1, 2, 3, 4])
    verifier = ChainVerifier(COMMITTEE, GOVERNANCE)
    verifier.add_closures([closure["closure"]])
    assert verifier.current.epoch == 1
    assert verifier.current.unlock
    votes = tuple(Vote.create(COMMITTEE, member, signed.transfer) for member in MEMBERS[:5])
    assert verifier.verify(QuorumCertificate(signed.transfer, votes, 0))
    other = spend(0, "other").transfer
    forged = tuple(Vote.create(COMMITTEE, member, other) for member in MEMBERS[:5])
    assert not verifier.verify(QuorumCertificate(other, forged, 0))


# --- The genesis -------------------------------------------------------------------------------------


def test_a_genesis_carries_the_setting(tmp_path):
    genesis = write_genesis(
        tmp_path / "g.json",
        [m.public_key for m in MEMBERS],
        1,
        {ALICE: 10},
        unlock=True,
    )
    assert genesis.committee.unlock
    assert parse_genesis((tmp_path / "g.json").read_text()).committee.quorum == 5


def test_a_genesis_without_it_is_standard(tmp_path):
    genesis = write_genesis(tmp_path / "g.json", [m.public_key for m in STANDARD_MEMBERS], 1, {ALICE: 10})
    assert not genesis.committee.unlock
    assert "unlock" not in (tmp_path / "g.json").read_text()


@pytest.mark.parametrize("value", ["yes", 1, None])
def test_a_genesis_with_a_bad_setting_is_refused(tmp_path, value):
    write_genesis(tmp_path / "g.json", [m.public_key for m in MEMBERS], 1, {ALICE: 10}, unlock=True)
    data = json.loads((tmp_path / "g.json").read_text())
    data["unlock"] = value
    with pytest.raises(DeploymentError):
        parse_genesis(json.dumps(data))


# --- Real nodes ---------------------------------------------------------------------------------------


def wait_until(condition, seconds=30.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return condition()


def test_real_nodes_with_six_members_certify_change_epoch_and_stay_equal(tmp_path):
    tag = tmp_path.name[-8:].replace("_", "-")
    nodes = [
        Node(
            f"u{index}-{tag}",
            GENESIS,
            quorum=QuorumConfig(
                COMMITTEE,
                member,
                tmp_path / f"{index}.sqlite",
                create=True,
                sync_interval=0.2,
                governance=GOVERNANCE,
            ),
        )
        for index, member in enumerate(MEMBERS)
    ]

    for node in nodes:
        node.start()

    try:
        for low in range(6):
            for high in range(low + 1, 6):
                host, port = nodes[high].address()
                assert nodes[low].connect_peer(Peer(node_id=nodes[high].node_id, host=host, port=port))

        assert nodes[0].submit(spend(0))
        assert wait_until(lambda: all(n.state.nonce(ALICE) == 1 for n in nodes))
        change = EpochChange.create(COMMITTEE, COMMITTEE.members, 1, GOVERNANCE, SIGNERS[:2])
        nodes[1].propose_epoch_change(change)
        assert wait_until(lambda: all(n._quorum.replica.committee.epoch == 1 for n in nodes))
        assert nodes[0].submit(spend(1))
        assert wait_until(lambda: all(n.state.nonce(ALICE) == 2 for n in nodes))
        assert len({n.state.root() for n in nodes}) == 1
    finally:
        for node in nodes:
            node.stop()
