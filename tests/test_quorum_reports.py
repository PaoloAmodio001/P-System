"""A closure must survive the death of who proposed it.

Each member votes for one closure per epoch, for good, and the reports of a retry can be another
quorum, so another closure. Before this was handled, one proposer that died at the wrong moment and
one retry left an epoch that could never close, with every member refusing to vote on events: the
whole committee stopped for good.
"""

import json

import pytest

from core.attestation import Committee, EpochChange, Governance
from core.event import Transfer
from core.signed_event import SignedTransfer
from core.state import State
from crypto.identity import Identity
from network.message import decode_closure_vote_request, encode_closure_locked
from network.quorum import QuorumDriver, QuorumReplica, SqliteVoteStore

SENDER = Identity.create()
GENESIS = State({SENDER.identity_id: 100})
SIGNERS = [Identity.create() for _ in range(3)]
GOVERNANCE = Governance(tuple(sorted(s.public_key for s in SIGNERS)), 2)
MEMBERS = sorted((Identity.create() for _ in range(4)), key=lambda m: m.public_key)
COMMITTEE = Committee.create([m.public_key for m in MEMBERS], 1, GENESIS)
CHANGE = EpochChange.create(
    COMMITTEE, [m.public_key for m in MEMBERS], 1, GOVERNANCE, SIGNERS[:2]
)
SPEND = SignedTransfer.create(SENDER, Transfer(SENDER.identity_id, "bob", 1, 0))


def wire(message: dict) -> dict:
    return json.loads(json.dumps(message))


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class Cluster:
    def __init__(self, directory):
        self.directory = directory
        self.clock = Clock()
        self.stores = {}
        self.drivers = {}
        for index in range(4):
            self.open(index, create=True)

    def open(self, index, create=False):
        store = SqliteVoteStore(
            self.directory / f"{index}.sqlite",
            COMMITTEE,
            MEMBERS[index].public_key,
            create=create,
            governance=GOVERNANCE,
        )
        replica = QuorumReplica(MEMBERS[index], GENESIS, store, lambda event: True)
        self.stores[index] = store
        self.drivers[index] = QuorumDriver(replica, governance=GOVERNANCE, clock=self.clock)

    def restart(self, index):
        self.stores[index].close()
        self.open(index)

    def close(self):
        for store in self.stores.values():
            store.close()

    def deliver(self, source, message, targets):
        """Send to each target, and bring all the answers back to `source`, in full."""
        pending = [(source, target, message) for target in targets]
        while pending:
            sender, target, current = pending.pop(0)
            output = self.drivers[target].handle_message(wire(current))
            for reply in output.replies:
                pending.append((target, sender, reply))
            for broadcast in output.broadcasts:
                for other in self.drivers:
                    if other != target and other in targets + [source]:
                        pending.append((target, other, broadcast))

    def epochs(self):
        return [driver.committee.epoch for driver in self.drivers.values()]


@pytest.fixture
def cluster(tmp_path):
    made = Cluster(tmp_path)
    yield made
    made.close()


def die_after_two_votes(cluster):
    """Node 3 proposes, members 0 and 1 vote on its closure, and it dies before hearing them."""
    start = cluster.drivers[3].propose_epoch_change(CHANGE)
    reports = [
        cluster.drivers[index].handle_message(wire(start.broadcasts[0])).replies[0]
        for index in (0, 1)
    ]
    request = None
    for report in reports:
        output = cluster.drivers[3].handle_message(wire(report))
        if output.broadcasts:
            request = output.broadcasts[0]
    assert request["type"] == "CLOSURE_VOTE_REQUEST"
    for index in (0, 1):
        assert cluster.drivers[index].handle_message(wire(request)).replies[0]["type"] == "CLOSURE_VOTE"
    return decode_closure_vote_request(request)


def test_a_retry_by_another_node_finishes_the_closure_already_voted(cluster):
    first = die_after_two_votes(cluster)
    assert first.digest

    # Reports of 2, 0 and 3: another quorum than 3, 0, 1, so on its own another closure.
    output = cluster.drivers[2].propose_epoch_change(CHANGE)
    cluster.deliver(2, output.broadcasts[0], [0, 3, 1])
    for broadcast in output.broadcasts[1:]:
        cluster.deliver(2, broadcast, [0, 3, 1])

    assert cluster.drivers[2].committee.epoch == 1
    assert cluster.stores[2].closures()[0].digest == first.digest


def test_a_retry_by_the_same_node_after_a_restart_uses_its_own_vote(cluster):
    first = die_after_two_votes(cluster)
    cluster.restart(3)
    output = cluster.drivers[3].propose_epoch_change(CHANGE)
    requests = [m for m in output.broadcasts if m["type"] == "CLOSURE_VOTE_REQUEST"]
    assert requests and decode_closure_vote_request(requests[0]).digest == first.digest


def test_a_member_that_voted_takes_over_after_a_while(cluster):
    first = die_after_two_votes(cluster)
    assert not cluster.drivers[0].retry().broadcasts
    cluster.clock.now += QuorumDriver.EPOCH_RETRY_SECONDS + 1
    output = cluster.drivers[0].retry()
    assert [m["type"] for m in output.broadcasts] == ["CLOSURE_VOTE_REQUEST"]
    cluster.deliver(0, output.broadcasts[0], [1, 2])
    assert cluster.drivers[0].committee.epoch == 1
    assert cluster.stores[0].closures()[0].digest == first.digest


def test_a_vote_survives_a_restart_for_the_takeover(cluster):
    first = die_after_two_votes(cluster)
    cluster.restart(0)
    cluster.clock.now += QuorumDriver.EPOCH_RETRY_SECONDS + 1
    output = cluster.drivers[0].retry()
    assert decode_closure_vote_request(output.broadcasts[0]).digest == first.digest


def test_a_proposer_sends_again_what_got_lost(cluster):
    output = cluster.drivers[0].propose_epoch_change(CHANGE)
    assert [m["type"] for m in output.broadcasts] == ["EPOCH_CHANGE"]
    assert not cluster.drivers[0].retry().broadcasts
    cluster.clock.now += QuorumDriver.EPOCH_RETRY_SECONDS + 1
    assert [m["type"] for m in cluster.drivers[0].retry().broadcasts] == ["EPOCH_CHANGE"]
    # Right after sending it waits again.
    assert not cluster.drivers[0].retry().broadcasts


def test_nothing_to_retry_without_a_closure_in_progress(cluster):
    cluster.clock.now += QuorumDriver.EPOCH_RETRY_SECONDS + 1
    assert all(not driver.retry().broadcasts for driver in cluster.drivers.values())


def test_after_a_closure_nothing_is_retried(cluster):
    die_after_two_votes(cluster)
    cluster.clock.now += QuorumDriver.EPOCH_RETRY_SECONDS + 1
    output = cluster.drivers[0].retry()
    cluster.deliver(0, output.broadcasts[0], [1, 2])
    cluster.clock.now += QuorumDriver.EPOCH_RETRY_SECONDS + 1
    assert not cluster.drivers[0].retry().broadcasts


def test_each_member_still_signs_one_closure(cluster):
    # The rule that makes the closure unique is not touched by any of this.
    first = die_after_two_votes(cluster)
    reports = [
        cluster.drivers[index].replica.report_epoch(CHANGE.change_id) for index in (1, 2, 3)
    ]
    other = type(first)(CHANGE, tuple(sorted(reports, key=lambda r: r.validator)))
    assert other.digest != first.digest
    assert cluster.drivers[0].replica.vote_for_closure(other, GOVERNANCE) is None
    assert cluster.drivers[0].replica.vote_for_closure(first, GOVERNANCE) is not None


def test_a_member_tells_of_the_closure_it_voted_when_asked_for_another(cluster):
    first = die_after_two_votes(cluster)
    reports = [
        cluster.drivers[index].replica.report_epoch(CHANGE.change_id) for index in (1, 2, 3)
    ]
    other = type(first)(CHANGE, tuple(sorted(reports, key=lambda r: r.validator)))
    from network.message import encode_closure_vote_request

    output = cluster.drivers[0].handle_message(wire(encode_closure_vote_request(other)))
    assert [m["type"] for m in output.replies] == ["CLOSURE_LOCKED"]


def test_a_member_says_so_on_a_new_order_too(cluster):
    die_after_two_votes(cluster)
    from network.message import encode_epoch_change

    output = cluster.drivers[0].handle_message(wire(encode_epoch_change(CHANGE)))
    assert [m["type"] for m in output.replies] == ["CLOSURE_LOCKED", "EPOCH_REPORT"]


def test_an_invalid_closure_cannot_be_adopted(cluster):
    first = die_after_two_votes(cluster)
    cluster.drivers[2].propose_epoch_change(CHANGE)
    broken = type(first)(CHANGE, first.reports[:1])
    before = cluster.drivers[2]._candidate
    output = cluster.drivers[2].handle_message(wire(encode_closure_locked(broken)))
    assert not output.broadcasts
    assert cluster.drivers[2]._candidate is before


def test_a_closure_is_adopted_only_by_a_proposer_of_that_order(cluster):
    first = die_after_two_votes(cluster)
    output = cluster.drivers[2].handle_message(wire(encode_closure_locked(first)))
    assert not output.broadcasts
    assert cluster.drivers[2]._candidate is None


def test_a_closure_is_adopted_once(cluster):
    first = die_after_two_votes(cluster)
    cluster.drivers[2].propose_epoch_change(CHANGE)
    output = cluster.drivers[2].handle_message(wire(encode_closure_locked(first)))
    assert [m["type"] for m in output.broadcasts] == ["CLOSURE_VOTE_REQUEST"]
    assert not cluster.drivers[2].handle_message(wire(encode_closure_locked(first))).broadcasts


def test_a_vote_for_another_order_is_not_offered(cluster):
    die_after_two_votes(cluster)
    keys = [Identity.create().public_key for _ in range(4)]
    different = EpochChange.create(COMMITTEE, keys, 1, GOVERNANCE, SIGNERS[:2])
    from network.message import encode_epoch_change

    output = cluster.drivers[0].handle_message(wire(encode_epoch_change(different)))
    assert [m["type"] for m in output.replies] == ["EPOCH_REPORT"]


def test_a_stored_closure_that_does_not_verify_is_not_taken_over(cluster, tmp_path):
    import sqlite3

    die_after_two_votes(cluster)
    cluster.stores[0].close()
    connection = sqlite3.connect(tmp_path / "0.sqlite")
    row = connection.execute("SELECT closure FROM closure_votes").fetchone()
    closure = json.loads(row[0])
    closure["reports"] = closure["reports"][:1]
    connection.execute("UPDATE closure_votes SET closure = ?", (json.dumps(closure),))
    connection.commit()
    connection.close()
    cluster.open(0)
    cluster.clock.now += QuorumDriver.EPOCH_RETRY_SECONDS + 1
    assert not cluster.drivers[0].retry().broadcasts
