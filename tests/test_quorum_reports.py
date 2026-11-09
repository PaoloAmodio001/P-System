"""A closure takes no votes (formal/lean/PSystem/QuorumReports.lean).

An order of governance and any quorum of reports is a closure. Before this, one proposer that died at
the wrong moment and one retry could stop the whole committee for good, and two proposers at once
could too: split_closures_block. Here two proposers race, die and come back, and what is left to block
an epoch is a governance that signs two orders.
"""

import json
import sqlite3
import time

import pytest

from core.attestation import Committee, EpochChange, EpochClosure, EpochReport, Governance
from core.event import Transfer
from core.signed_event import SignedTransfer
from core.state import State
from crypto.identity import Identity
from network.message import decode_epoch_closure, encode_epoch_change, encode_epoch_closure, encode_epoch_report
from network.node import Node
from network.peer import Peer
from network.quorum import QuorumConfig, QuorumDriver, QuorumReplica, SqliteVoteStore
from network.remote_signer import SignerGuard
from sdk.client import ChainVerifier

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


OTHER_MEMBERS = sorted((Identity.create() for _ in range(4)), key=lambda m: m.public_key)
OTHER = EpochChange.create(
    COMMITTEE, [m.public_key for m in OTHER_MEMBERS], 1, GOVERNANCE, SIGNERS[:2]
)


def report_of(cluster, index, change=CHANGE):
    [reply] = cluster.drivers[index].handle_message(wire(encode_epoch_change(change))).replies
    return reply


# --- One order for each epoch ---------------------------------------------------------------------


def test_a_member_reports_for_one_order_for_good(cluster):
    assert report_of(cluster, 1)["type"] == "EPOCH_REPORT"
    assert cluster.drivers[1].handle_message(wire(encode_epoch_change(OTHER))).replies == ()


def test_the_lock_on_the_order_survives_a_restart(cluster):
    report_of(cluster, 1)
    cluster.restart(1)
    assert cluster.drivers[1].handle_message(wire(encode_epoch_change(OTHER))).replies == ()
    assert cluster.drivers[1].replica.reported_change().change_id == CHANGE.change_id


def test_the_same_order_again_gets_the_same_report(cluster):
    # So a second proposer can finish what a lost one began.
    assert report_of(cluster, 1) == report_of(cluster, 1)


def test_a_proposer_locked_on_one_order_gives_no_report_for_another(cluster):
    report_of(cluster, 0)
    cluster.drivers[0].propose_epoch_change(OTHER)
    assert cluster.drivers[0]._reports == {}


def test_two_orders_cannot_both_get_a_quorum(cluster):
    for index in (0, 1):
        report_of(cluster, index, CHANGE)
    # The third and fourth member decide: two for each is all this can reach.
    for index in (2, 3):
        report_of(cluster, index, OTHER)
    for index in (0, 1):
        assert cluster.drivers[index].handle_message(wire(encode_epoch_change(OTHER))).replies == ()
    for index in (2, 3):
        assert cluster.drivers[index].handle_message(wire(encode_epoch_change(CHANGE))).replies == ()


def test_an_order_governance_did_not_sign_gets_no_report_and_no_lock(cluster):
    bad = EpochChange.create(COMMITTEE, COMMITTEE.members, 1, GOVERNANCE, SIGNERS[:1])
    assert cluster.drivers[1].handle_message(wire(encode_epoch_change(bad))).replies == ()
    assert cluster.drivers[1].replica.reported_change() is None
    assert report_of(cluster, 1)["type"] == "EPOCH_REPORT"


def test_a_guard_gives_one_order_for_each_committee(tmp_path):
    guard = SignerGuard(tmp_path / "guard.sqlite")
    report = EpochReport._payload(COMMITTEE, CHANGE.change_id, ())
    other = EpochReport._payload(COMMITTEE, OTHER.change_id, ())
    assert guard.permit(report)
    assert guard.permit(report)
    assert not guard.permit(other)
    guard.close()


# --- Any quorum of reports is a closure ---------------------------------------------------------


def closure_of(cluster, indexes, change=CHANGE):
    reports = {}
    for index in indexes:
        reply = report_of(cluster, index, change)
        reports[reply["report"]["validator"]] = reply

    collector = cluster.drivers[indexes[0]]
    collector._change = change
    collector._reports = {}
    closure = None

    for reply in reports.values():
        output = collector.handle_message(wire(reply))
        for message in output.broadcasts:
            if message["type"] == "EPOCH_CLOSURE":
                closure = message

    return closure


def test_two_proposers_with_different_quorums_both_close_it(cluster):
    # This is what used to block for good: `split_closures_block`.
    first = cluster.drivers[0]
    second = cluster.drivers[3]
    start_first = first.propose_epoch_change(CHANGE)
    start_second = second.propose_epoch_change(CHANGE)

    for message in (cluster.drivers[1].handle_message(wire(start_first.broadcasts[0])).replies):
        first.handle_message(wire(message))
    for message in (cluster.drivers[2].handle_message(wire(start_first.broadcasts[0])).replies):
        output_first = first.handle_message(wire(message))
    for message in (cluster.drivers[1].handle_message(wire(start_second.broadcasts[0])).replies):
        second.handle_message(wire(message))
    for message in (cluster.drivers[2].handle_message(wire(start_second.broadcasts[0])).replies):
        output_second = second.handle_message(wire(message))

    closure_first = decode_epoch_closure(wire(output_first.broadcasts[0]))
    closure_second = decode_epoch_closure(wire(output_second.broadcasts[0]))
    assert closure_first.digest != closure_second.digest
    assert first.committee.committee_id == second.committee.committee_id
    assert first.committee.epoch == second.committee.epoch == 1


def test_a_node_takes_either_closure_and_the_same_committee_follows(cluster):
    first = cluster.drivers[0]
    second = cluster.drivers[3]
    closures = []

    for proposer in (first, second):
        start = proposer.propose_epoch_change(CHANGE)
        for index in (1, 2):
            for reply in cluster.drivers[index].handle_message(wire(start.broadcasts[0])).replies:
                output = proposer.handle_message(wire(reply))
        closures.append(output.broadcasts[0])

    assert closures[0] != closures[1]
    cluster.drivers[1].handle_message(wire(closures[0]))
    cluster.drivers[2].handle_message(wire(closures[1]))
    assert cluster.drivers[1].committee.committee_id == cluster.drivers[2].committee.committee_id
    assert cluster.drivers[1].committee.epoch == 1


def test_a_vote_after_a_report_is_locked_on_either_closure(cluster):
    # What a closure must do, whichever it is: a certified event binds the next committee.
    signed = SPEND
    for index in (0, 1, 2):
        assert cluster.drivers[index].replica.handle_vote_request(signed.transfer, signed) is not None

    closure = closure_of(cluster, [0, 1, 2])
    assert closure is not None
    other_version = SignedTransfer.create(SENDER, Transfer(SENDER.identity_id, "carol", 1, 0))
    driver = cluster.drivers[0]
    assert driver.committee.epoch == 1
    assert driver.replica.handle_vote_request(other_version.transfer, other_version) is None


def test_a_proposer_that_died_is_replaced_by_a_member_that_reported(cluster):
    start = cluster.drivers[3].propose_epoch_change(CHANGE)
    for index in (0, 1, 2):
        cluster.drivers[index].handle_message(wire(start.broadcasts[0]))
    # Node 3 is gone, and nobody got anything back.
    assert cluster.epochs()[:3] == [0, 0, 0]
    cluster.clock.now += QuorumDriver.EPOCH_RETRY_SECONDS + 1
    retry = cluster.drivers[0].retry()
    assert [m["type"] for m in retry.broadcasts] == ["EPOCH_CHANGE"]
    cluster.deliver(0, retry.broadcasts[0], [1, 2])
    assert cluster.drivers[0].committee.epoch == 1


def test_a_member_restarted_after_its_report_still_finishes_it(cluster):
    report_of(cluster, 0)
    report_of(cluster, 1)
    report_of(cluster, 2)
    cluster.restart(0)
    cluster.clock.now += QuorumDriver.EPOCH_RETRY_SECONDS + 1
    retry = cluster.drivers[0].retry()
    assert [m["type"] for m in retry.broadcasts] == ["EPOCH_CHANGE"]
    cluster.deliver(0, retry.broadcasts[0], [1, 2])
    assert cluster.drivers[0].committee.epoch == 1


def test_nothing_to_retry_without_a_report(cluster):
    cluster.clock.now += QuorumDriver.EPOCH_RETRY_SECONDS + 1
    assert cluster.drivers[0].retry().broadcasts == ()


def test_a_retry_waits(cluster):
    report_of(cluster, 0)
    assert cluster.drivers[0].retry().broadcasts == ()
    cluster.clock.now += QuorumDriver.EPOCH_RETRY_SECONDS + 1
    assert cluster.drivers[0].retry().broadcasts
    assert cluster.drivers[0].retry().broadcasts == ()


def test_a_halted_node_does_not_retry(cluster):
    from core.attestation import QuorumCertificate, Vote

    report_of(cluster, 0)

    def certificate(receiver):
        event = Transfer(SENDER.identity_id, receiver, 1, 0)
        return QuorumCertificate(
            event, tuple(Vote.create(COMMITTEE, m, event) for m in MEMBERS[:3])
        )

    cluster.drivers[0].replica.record_halt(certificate("x"), certificate("y"))
    cluster.clock.now += QuorumDriver.EPOCH_RETRY_SECONDS + 1
    assert cluster.drivers[0].retry().broadcasts == ()


def test_a_retry_sends_the_closure_if_the_reports_are_already_in(cluster):
    driver = cluster.drivers[0]
    start = driver.propose_epoch_change(CHANGE)
    assert start.broadcasts
    for index in (1, 2):
        driver.handle_message(wire(report_of(cluster, index)))
    assert driver.committee.epoch == 1


def test_reports_are_counted_once_each(cluster):
    driver = cluster.drivers[0]
    driver.propose_epoch_change(CHANGE)
    reply = report_of(cluster, 1)
    driver.handle_message(wire(reply))
    driver.handle_message(wire(reply))
    assert driver.committee.epoch == 0


def test_a_report_for_another_order_is_not_counted(cluster):
    driver = cluster.drivers[0]
    driver.propose_epoch_change(CHANGE)
    driver.handle_message(wire(report_of(cluster, 1, OTHER)))
    assert list(driver._reports) == [0]


def test_a_report_with_nothing_proposed_is_not_counted(cluster):
    driver = cluster.drivers[0]
    driver.handle_message(wire(report_of(cluster, 1)))
    assert driver._reports == {}


def test_a_report_with_a_bad_signature_is_not_counted(cluster):
    driver = cluster.drivers[0]
    driver.propose_epoch_change(CHANGE)
    bad = EpochReport(1, (), b"\0" * 64)
    driver.handle_message(wire(encode_epoch_report(CHANGE.change_id, bad)))
    assert list(driver._reports) == [0]


# --- What a closure must be -------------------------------------------------------------------------


def reports_for(count, change=CHANGE, votes=()):
    return tuple(
        EpochReport.create(COMMITTEE, MEMBERS[index], change.change_id, votes)
        for index in range(count)
    )


def test_a_quorum_of_reports_verifies():
    assert EpochClosure(CHANGE, reports_for(3)).verify(GOVERNANCE, COMMITTEE)
    assert EpochClosure(CHANGE, reports_for(4)).verify(GOVERNANCE, COMMITTEE)


def test_below_a_quorum_it_does_not():
    assert not EpochClosure(CHANGE, reports_for(2)).verify(GOVERNANCE, COMMITTEE)


def test_reports_repeated_or_out_of_order_do_not():
    reports = reports_for(3)
    assert not EpochClosure(CHANGE, (reports[0], reports[0], reports[1])).verify(GOVERNANCE, COMMITTEE)
    assert not EpochClosure(CHANGE, tuple(reversed(reports))).verify(GOVERNANCE, COMMITTEE)


def test_a_forged_report_does_not():
    reports = reports_for(3)
    forged = EpochReport(reports[0].validator, (), b"\0" * 64)
    assert not EpochClosure(CHANGE, (forged, *reports[1:])).verify(GOVERNANCE, COMMITTEE)


def test_a_report_for_another_order_does_not():
    reports = reports_for(3)
    others = reports_for(1, OTHER)
    assert not EpochClosure(CHANGE, (others[0], *reports[1:])).verify(GOVERNANCE, COMMITTEE)


def test_an_order_governance_did_not_sign_does_not():
    bad = EpochChange.create(COMMITTEE, COMMITTEE.members, 1, GOVERNANCE, SIGNERS[:1])
    assert not EpochClosure(bad, reports_for(3, bad)).verify(GOVERNANCE, COMMITTEE)


def test_any_valid_closure_is_taken_by_a_node_and_a_client(cluster):
    closure = EpochClosure(CHANGE, reports_for(3))
    cluster.drivers[3].handle_message(wire(encode_epoch_closure(closure)))
    assert cluster.drivers[3].committee.epoch == 1
    verifier = ChainVerifier(COMMITTEE, GOVERNANCE)
    verifier.add_closures([encode_epoch_closure(closure)["closure"]])
    assert verifier.current.epoch == 1


def test_a_closure_with_votes_on_the_wire_is_refused(cluster):
    message = wire(encode_epoch_closure(EpochClosure(CHANGE, reports_for(3))))
    message["closure"]["votes"] = []
    with pytest.raises(ValueError):
        decode_epoch_closure(message)


def test_a_closure_forgets_what_the_node_was_gathering(cluster):
    assert cluster.drivers[1].submit(SPEND).broadcasts
    assert cluster.stores[1].gathering() == [SPEND]
    closure = decode_epoch_closure(wire(closure_of(cluster, (0, 1, 2))))
    cluster.stores[1].install_closure(closure)
    assert cluster.stores[1].gathering() == []
    # Not only out of sight: a row of an ended epoch would stay in the file for good.
    assert cluster.stores[1]._connection.execute("SELECT COUNT(*) FROM gathering").fetchone() == (0,)
    cluster.restart(1)
    assert cluster.drivers[1].gathering_count == 0


# --- From an older file ------------------------------------------------------------------------------


def downgrade(path, closure=None):
    connection = sqlite3.connect(path)
    connection.execute("DROP TABLE gathering")
    connection.execute("DROP TABLE report_locks")
    connection.execute("DROP TABLE snapshot")
    connection.execute("DROP TABLE floors")
    connection.execute(
        "CREATE TABLE closure_votes (epoch INTEGER PRIMARY KEY, digest TEXT NOT NULL, closure TEXT)"
    )
    if closure is not None:
        body = encode_epoch_closure(closure)["closure"]
        connection.execute(
            "INSERT INTO closure_votes (epoch, digest, closure) VALUES (0, ?, ?)",
            (closure.digest, json.dumps(body)),
        )
    connection.execute("UPDATE meta SET value = '4' WHERE key = 'schema_version'")
    connection.commit()
    connection.close()


def test_a_closure_voted_for_becomes_the_lock_on_its_order(cluster):
    cluster.stores[1].close()
    path = cluster.directory / "1.sqlite"
    downgrade(path, EpochClosure(CHANGE, reports_for(3)))
    cluster.open(1)
    assert cluster.drivers[1].replica.reported_change().change_id == CHANGE.change_id
    assert cluster.drivers[1].handle_message(wire(encode_epoch_change(OTHER))).replies == ()
    assert report_of(cluster, 1)["type"] == "EPOCH_REPORT"


def test_an_epoch_closed_with_no_order_on_file_gives_no_more_reports(cluster):
    report_of(cluster, 1)
    cluster.stores[1].close()
    path = cluster.directory / "1.sqlite"
    downgrade(path)
    cluster.open(1)
    # It may have reported for any order, so a report now could be for a second one.
    assert cluster.drivers[1].handle_message(wire(encode_epoch_change(CHANGE))).replies == ()


def test_closures_on_file_lose_their_votes(cluster):
    closure = closure_of(cluster, [0, 1, 2])
    assert closure is not None
    cluster.stores[0].close()
    path = cluster.directory / "0.sqlite"
    connection = sqlite3.connect(path)
    body = json.loads(connection.execute("SELECT closure FROM closures").fetchone()[0])
    body["votes"] = [{"validator": 0, "signature": "00" * 64}]
    connection.execute("UPDATE closures SET closure = ?", (json.dumps(body),))
    connection.commit()
    connection.close()
    downgrade(path)
    cluster.open(0)
    assert cluster.drivers[0].committee.epoch == 1


# --- Old closures of a node that prunes ----------------------------------------------------------


def run_epochs(tmp_path, count):
    """A store through `count` epochs with one event locked in each, and a snapshot and floor at the end."""
    store = SqliteVoteStore(
        tmp_path / "chain.sqlite",
        COMMITTEE,
        MEMBERS[0].public_key,
        create=True,
        governance=GOVERNANCE,
    )
    replica = QuorumReplica(MEMBERS[0], GENESIS, store, lambda event: True)
    closures = []

    for epoch in range(count):
        current = replica.committee
        change = EpochChange.create(current, current.members, 1, GOVERNANCE, SIGNERS[:2])
        signed = SignedTransfer.create(SENDER, Transfer(SENDER.identity_id, "bob", 1, 100 + epoch))
        reports = tuple(
            EpochReport.create(current, member, change.change_id, (signed,))
            for member in MEMBERS[:3]
        )
        closure = EpochClosure(change, reports)
        assert closure.verify(GOVERNANCE, current)
        replica.install_closure(closure)
        closures.append(closure)

    return store, replica, closures


def test_old_closures_become_headers_and_the_last_stays_whole(tmp_path):
    from core.attestation import Snapshot

    store, replica, closures = run_epochs(tmp_path, 3)
    store.apply_floor(Snapshot(3, State({}, {}), ()))
    assert [c.digest for c in store.closures(2)] == [closures[2].digest]
    # Asked for more than it has whole, it gives nothing: a header must never leave this node.
    assert store.closures(0) == []
    assert store.closures(1) == []
    store.close()

    reopened = SqliteVoteStore(
        tmp_path / "chain.sqlite",
        COMMITTEE,
        MEMBERS[0].public_key,
        governance=GOVERNANCE,
    )
    assert reopened.committee.epoch == 3
    assert reopened.committee.committee_id == replica.committee.committee_id
    reopened.close()


def test_a_header_takes_less_room_and_a_node_still_knows_its_locks(tmp_path):
    from core.attestation import Snapshot

    store, _, closures = run_epochs(tmp_path, 3)
    connection = store._connection
    before = connection.execute("SELECT length(closure) FROM closures WHERE epoch = 0").fetchone()[0]
    store.apply_floor(Snapshot(3, State({}, {}), ()))
    after = connection.execute("SELECT length(closure) FROM closures WHERE epoch = 0").fetchone()[0]
    assert after < before
    old = closures[0].locks(COMMITTEE)[0]
    assert store.is_locked_event(old)
    store.close()


@pytest.mark.parametrize(
    "change",
    [
        lambda header: header.update(header=header["header"][:2]),
        lambda header: header["header"][0].__setitem__(2, "00" * 64),
        lambda header: header["header"][0].__setitem__(1, "00" * 32),
        lambda header: header["header"].__setitem__(1, header["header"][0]),
        lambda header: header["change"].update(previous="00" * 32),
        lambda header: header["change"].update(signatures=[]),
    ],
)
def test_an_altered_header_does_not_open(tmp_path, change):
    from core.attestation import Snapshot
    from network.quorum import VoteStoreError

    store, _, _ = run_epochs(tmp_path, 3)
    store.apply_floor(Snapshot(3, State({}, {}), ()))
    store.close()
    connection = sqlite3.connect(tmp_path / "chain.sqlite")
    header = json.loads(
        connection.execute("SELECT closure FROM closures WHERE epoch = 0").fetchone()[0]
    )
    change(header)
    connection.execute(
        "UPDATE closures SET closure = ? WHERE epoch = 0",
        (json.dumps(header),),
    )
    connection.commit()
    connection.close()

    with pytest.raises(VoteStoreError):
        SqliteVoteStore(
            tmp_path / "chain.sqlite",
            COMMITTEE,
            MEMBERS[0].public_key,
            governance=GOVERNANCE,
        )


def test_an_unreadable_header_does_not_open(tmp_path):
    from core.attestation import Snapshot
    from network.quorum import VoteStoreError

    store, _, _ = run_epochs(tmp_path, 3)
    store.apply_floor(Snapshot(3, State({}, {}), ()))
    store.close()
    connection = sqlite3.connect(tmp_path / "chain.sqlite")
    connection.execute("""UPDATE closures SET closure = '{"change": {}, "header": 1}' WHERE epoch = 0""")
    connection.commit()
    connection.close()

    with pytest.raises(VoteStoreError):
        SqliteVoteStore(
            tmp_path / "chain.sqlite",
            COMMITTEE,
            MEMBERS[0].public_key,
            governance=GOVERNANCE,
        )


# --- With real nodes ------------------------------------------------------------------------------


def wait_until(condition, seconds=30.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return condition()


def test_two_real_proposers_at_once_change_the_committee_on_every_node(tmp_path):
    tag = tmp_path.name[-8:].replace("_", "-")
    nodes = [
        Node(
            f"r{index}-{tag}",
            GENESIS,
            quorum=QuorumConfig(
                COMMITTEE,
                MEMBERS[index],
                tmp_path / f"{index}.sqlite",
                create=True,
                sync_interval=0.2,
                governance=GOVERNANCE,
            ),
        )
        for index in range(4)
    ]

    for node in nodes:
        node.start()

    try:
        for low in range(4):
            for high in range(low + 1, 4):
                host, port = nodes[high].address()
                assert nodes[low].connect_peer(
                    Peer(node_id=nodes[high].node_id, host=host, port=port)
                )

        assert nodes[0].submit(SPEND)
        assert wait_until(lambda: all(n.state.nonce(SENDER.identity_id) == 1 for n in nodes))
        nodes[0].propose_epoch_change(CHANGE)
        nodes[3].propose_epoch_change(CHANGE)
        assert wait_until(lambda: all(n._quorum.replica.committee.epoch == 1 for n in nodes))
        assert len({n._quorum.replica.committee.committee_id for n in nodes}) == 1
        assert len({n.state.root() for n in nodes}) == 1
    finally:
        for node in nodes:
            node.stop()
