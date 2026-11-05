"""A chain of committees (formal/lean/PSystem/QuorumEpochs.lean).

The rules, without a network: governance orders, a quorum reports and stops voting, the
committee certifies one closure, and the locks bind the next committee. The messages pass
through JSON. The real network is in tests/test_quorum_differential_epochs.py.
"""

import json

import pytest

from core.attestation import (
    Committee,
    EpochChange,
    EpochClosure,
    EpochReport,
    Governance,
    QuorumCertificate,
    Vote,
    guilty_members,
)
from core.derive import StateDeriver
from core.event import Transfer
from core.signed_event import SignedTransfer
from core.state import State
from crypto.identity import Identity
from network.message import (
    decode_certificate,
    decode_epoch_change,
    decode_epoch_closure,
    decode_epoch_report,
    encode_certificate,
    encode_certificate_sync_request,
    encode_epoch_change,
    encode_epoch_closure,
    encode_epoch_report,
    encode_vote_request,
)
from network.quorum import QuorumDriver, QuorumReplica, SqliteVoteStore, VoteStoreError

SENDER = Identity.create()
ALICE = SENDER.identity_id
GENESIS = State({ALICE: 100})
SIGNERS = [Identity.create() for _ in range(3)]
GOVERNANCE = Governance(tuple(sorted(s.public_key for s in SIGNERS)), 2)


def by_key(identities):
    return sorted(identities, key=lambda identity: identity.public_key)


MEMBERS = by_key(Identity.create() for _ in range(4))
NEXT_MEMBERS = by_key(Identity.create() for _ in range(4))
COMMITTEE = Committee.create([m.public_key for m in MEMBERS], 1, GENESIS)


def wire(message: dict) -> dict:
    return json.loads(json.dumps(message))


def spend(nonce: int, receiver: str = "bob") -> SignedTransfer:
    return SignedTransfer.create(SENDER, Transfer(ALICE, receiver, 1, nonce))


def change_to(current: Committee, keys=None, signers=SIGNERS[:2], f=1) -> EpochChange:
    keys = keys if keys is not None else [m.public_key for m in NEXT_MEMBERS]
    return EpochChange.create(current, keys, f, GOVERNANCE, signers)


class Cluster:
    """Drivers of the committee, each with a file, and messages passed by hand."""

    def __init__(self, tmp_path, members=MEMBERS, committee=COMMITTEE, tag="a"):
        self.stores = []
        self.drivers = []
        self.tmp_path = tmp_path
        for index, member in enumerate(members):
            self.drivers.append(self.open(member, committee, f"{tag}{index}"))

    def open(self, member, committee, name, joining=False):
        store = SqliteVoteStore(
            self.tmp_path / f"{name}.sqlite",
            committee,
            member.public_key,
            create=True,
            governance=GOVERNANCE,
            joining=joining,
        )
        self.stores.append(store)
        replica = QuorumReplica(member, GENESIS, store, lambda _event: True)
        return QuorumDriver(replica, GOVERNANCE)

    def close(self):
        for store in self.stores:
            store.close()

    def certify(self, signed, voters, proposer=0):
        """Votes of `voters` reach `proposer`, which broadcasts the certificate."""
        proposer_driver = self.drivers[proposer]
        output = proposer_driver.submit(signed)
        for voter in voters:
            if voter == proposer:
                continue
            for reply in self.drivers[voter].handle_message(
                wire(encode_vote_request(signed))
            ).replies:
                output = proposer_driver.handle_message(wire(reply))
        return output

    def close_epoch(self, change, proposer=0, reporters=None):
        """The whole end of an epoch. Returns the closure, or None if it did not form."""
        driver = self.drivers[proposer]
        output = driver.propose_epoch_change(change)
        closure = next((m for m in output.broadcasts if m["type"] == "EPOCH_CLOSURE"), None)
        indexes = reporters if reporters is not None else range(len(self.drivers))

        for index in indexes:
            if index == proposer or closure is not None:
                continue
            for reply in self.drivers[index].handle_message(
                wire(encode_epoch_change(change))
            ).replies:
                out = driver.handle_message(wire(reply))
                for message in out.broadcasts:
                    if message["type"] == "EPOCH_CLOSURE":
                        closure = message

        if closure is None:
            return None

        for index, other in enumerate(self.drivers):
            if index != proposer:
                other.handle_message(wire(closure))

        return decode_epoch_closure(wire(closure))


@pytest.fixture
def cluster(tmp_path):
    made = Cluster(tmp_path)
    yield made
    made.close()


# --- Governance -------------------------------------------------------------------------


@pytest.mark.parametrize("threshold", [0, 1, 4, True, "2"])
def test_governance_refuses_a_bad_threshold(threshold):
    with pytest.raises(ValueError):
        Governance(GOVERNANCE.members, threshold)


def test_governance_is_never_one_key():
    with pytest.raises(ValueError):
        Governance(GOVERNANCE.members[:1], 1)


def test_governance_requires_sorted_distinct_keys():
    with pytest.raises(ValueError):
        Governance(tuple(reversed(GOVERNANCE.members)), 2)
    with pytest.raises(ValueError):
        Governance((GOVERNANCE.members[0],) * 3, 2)
    with pytest.raises(ValueError):
        Governance((b"short", GOVERNANCE.members[1]), 2)


def test_change_needs_the_threshold():
    assert change_to(COMMITTEE).verify(GOVERNANCE, COMMITTEE)
    assert not change_to(COMMITTEE, signers=SIGNERS[:1]).verify(GOVERNANCE, COMMITTEE)


def test_change_with_a_repeated_signer_does_not_reach_the_threshold():
    one = change_to(COMMITTEE, signers=SIGNERS[:1])
    repeated = EpochChange(
        one.previous_id,
        one.next_members,
        one.next_f,
        one.signatures * 2,
    )
    assert not repeated.verify(GOVERNANCE, COMMITTEE)


def test_change_signed_by_outsiders_is_refused():
    outsider = Identity.create()
    good = change_to(COMMITTEE)
    forged = EpochChange(
        good.previous_id,
        good.next_members,
        good.next_f,
        tuple((i, outsider.sign(good._payload(GOVERNANCE))) for i in (0, 1)),
    )
    assert not forged.verify(GOVERNANCE, COMMITTEE)


def test_change_binds_its_content():
    good = change_to(COMMITTEE)
    other = tuple(sorted(m.public_key for m in MEMBERS))
    altered = EpochChange(good.previous_id, other, good.next_f, good.signatures)
    assert not altered.verify(GOVERNANCE, COMMITTEE)


def test_change_for_another_committee_is_refused():
    other = Committee.create([m.public_key for m in NEXT_MEMBERS], 1, GENESIS)
    assert not change_to(other).verify(GOVERNANCE, COMMITTEE)


@pytest.mark.parametrize("f", [0, 2])
def test_change_to_an_invalid_committee_is_refused(f):
    # Three members and f = 1 is not 3f+1, whoever signed it.
    bad = EpochChange.create(COMMITTEE, [m.public_key for m in MEMBERS[:3]], f, GOVERNANCE, SIGNERS)
    assert not bad.verify(GOVERNANCE, COMMITTEE)


@pytest.mark.parametrize("index", [-1, 3, 99])
def test_change_with_a_signer_out_of_range_is_false_and_not_an_error(index):
    good = change_to(COMMITTEE)
    altered = EpochChange(
        good.previous_id,
        good.next_members,
        good.next_f,
        ((index, good.signatures[0][1]), good.signatures[1]),
    )
    assert not altered.verify(GOVERNANCE, COMMITTEE)


# --- Identity of a committee ------------------------------------------------------------


def test_id_of_a_first_committee_does_not_change_with_epochs():
    expected = Committee(COMMITTEE.members, 1, COMMITTEE.genesis_root).committee_id
    assert COMMITTEE.committee_id == expected


def test_next_committee_has_another_id_even_with_the_same_members():
    change = change_to(COMMITTEE, keys=[m.public_key for m in MEMBERS])
    following = change.next_committee(COMMITTEE)
    assert following.members == COMMITTEE.members
    assert following.committee_id != COMMITTEE.committee_id
    assert following.epoch == 1
    assert following.previous_id == COMMITTEE.committee_id


@pytest.mark.parametrize(
    "epoch,previous",
    [(-1, ""), (True, "a" * 64), ("1", "a" * 64), (0, "a" * 64), (1, ""), (1, "A" * 64)],
)
def test_committee_refuses_a_bad_place_in_the_chain(epoch, previous):
    with pytest.raises(ValueError):
        Committee(COMMITTEE.members, 1, COMMITTEE.genesis_root, epoch, previous)


def test_a_vote_of_an_old_epoch_is_not_valid_in_a_new_one():
    event = spend(0).transfer
    following = change_to(COMMITTEE, keys=[m.public_key for m in MEMBERS]).next_committee(
        COMMITTEE
    )
    vote = Vote.create(COMMITTEE, MEMBERS[0], event)
    assert vote.verify(COMMITTEE, event)
    assert not vote.verify(following, event)


def test_certificate_says_its_epoch():
    event = spend(0).transfer
    votes = tuple(Vote.create(COMMITTEE, MEMBERS[i], event) for i in range(3))
    assert QuorumCertificate(event, votes).verify(COMMITTEE)
    assert not QuorumCertificate(event, votes, 1).verify(COMMITTEE)
    assert not QuorumCertificate(event, votes, True).verify(COMMITTEE)


def test_certificate_of_a_later_epoch_keeps_its_epoch_on_the_wire():
    event = spend(0).transfer
    certificate = QuorumCertificate(
        event,
        tuple(Vote.create(COMMITTEE, MEMBERS[i], event) for i in range(3)),
        5,
    )
    decoded = decode_certificate(wire(encode_certificate(certificate)))
    assert decoded == certificate


@pytest.mark.parametrize("epoch", [0, -1, True, "1", None])
def test_certificate_with_a_bad_epoch_on_the_wire_is_a_value_error(epoch):
    event = spend(0).transfer
    message = wire(encode_certificate(QuorumCertificate(event, ())))
    message["epoch"] = epoch
    with pytest.raises(ValueError):
        decode_certificate(message)


# --- Reports ----------------------------------------------------------------------------


def test_report_round_trip(cluster):
    change = change_to(COMMITTEE)
    cluster.certify(spend(0), [0, 1, 2])
    report = cluster.drivers[1].replica.report_epoch(change)
    change_id, decoded = decode_epoch_report(
        wire(encode_epoch_report(change.change_id, report))
    )
    assert change_id == change.change_id
    assert decoded == report
    assert decoded.verify(COMMITTEE, change.change_id)


def test_report_holds_every_vote_and_only_those(cluster):
    driver = cluster.drivers[1]
    signed = [spend(0), spend(1)]
    for event in signed:
        driver.handle_message(wire(encode_vote_request(event)))
    report = driver.replica.report_epoch(change_to(COMMITTEE))
    assert {s.transfer.canonical() for s in report.votes} == {
        s.transfer.canonical() for s in signed
    }


def test_after_a_report_a_validator_votes_for_nothing(cluster):
    driver = cluster.drivers[1]
    driver.replica.report_epoch(change_to(COMMITTEE))
    output = driver.handle_message(wire(encode_vote_request(spend(0))))
    assert output.replies == ()
    assert driver.replica.votes() == []


def test_the_report_is_the_same_when_asked_again(cluster):
    # So a second proposer can finish what a lost one began.
    driver = cluster.drivers[1]
    driver.handle_message(wire(encode_vote_request(spend(0))))
    change = change_to(COMMITTEE)
    first = driver.replica.report_epoch(change)
    driver.handle_message(wire(encode_vote_request(spend(1))))
    assert driver.replica.report_epoch(change) == first


def test_closing_survives_a_restart(tmp_path):
    cluster = Cluster(tmp_path)
    driver = cluster.drivers[1]
    driver.replica.report_epoch(change_to(COMMITTEE))
    cluster.close()
    reopened = SqliteVoteStore(
        tmp_path / "a1.sqlite",
        COMMITTEE,
        MEMBERS[1].public_key,
        governance=GOVERNANCE,
    )
    assert reopened.epoch_is_closed()
    assert not reopened.record_vote(spend(0).transfer, spend(0))
    reopened.close()


def _report_for(member, committee, change_id, votes):
    return EpochReport.create(committee, member, change_id, votes)


def test_report_with_an_event_the_sender_did_not_sign_is_refused(cluster):
    # Otherwise a faulty validator could lock any account.
    change_id = change_to(COMMITTEE).change_id
    other = Identity.create()
    forged = SignedTransfer.create(other, Transfer(ALICE, "mallory", 1, 0))
    assert not _report_for(MEMBERS[3], COMMITTEE, change_id, [forged]).verify(
        COMMITTEE, change_id
    )
    bad_signature = SignedTransfer(
        spend(0).transfer,
        SENDER.public_key,
        b"\0" * 64,
    )
    assert not _report_for(MEMBERS[3], COMMITTEE, change_id, [bad_signature]).verify(
        COMMITTEE, change_id
    )


def test_report_binds_its_validator_change_and_votes():
    change_id = change_to(COMMITTEE).change_id
    report = _report_for(MEMBERS[0], COMMITTEE, change_id, [spend(0)])
    assert report.verify(COMMITTEE, change_id)
    assert not report.verify(COMMITTEE, "0" * 64)
    assert not EpochReport(1, report.votes, report.signature).verify(COMMITTEE, change_id)
    assert not EpochReport(0, (), report.signature).verify(COMMITTEE, change_id)
    assert not EpochReport(99, report.votes, report.signature).verify(COMMITTEE, change_id)


def test_report_with_votes_out_of_order_is_refused():
    change_id = change_to(COMMITTEE).change_id
    report = _report_for(MEMBERS[0], COMMITTEE, change_id, [spend(0), spend(1)])
    backwards = tuple(reversed(report.votes))
    assert not EpochReport(0, backwards, report.signature).verify(COMMITTEE, change_id)


# --- The end of an epoch ----------------------------------------------------------------


def test_whole_epoch_change(cluster):
    cluster.certify(spend(0), [0, 1, 2])
    closure = cluster.close_epoch(change_to(COMMITTEE))

    assert closure is not None
    assert closure.verify(GOVERNANCE, COMMITTEE)
    for driver in cluster.drivers:
        assert driver.committee.epoch == 1
        assert driver.committee.members == tuple(m.public_key for m in NEXT_MEMBERS)


def test_a_quorum_of_reports_is_enough(cluster):
    assert cluster.close_epoch(change_to(COMMITTEE), reporters=[0, 1, 2])
    assert cluster.drivers[0].committee.epoch == 1


def test_too_few_reports_give_no_closure(cluster):
    assert cluster.close_epoch(change_to(COMMITTEE), reporters=[0, 1]) is None
    assert cluster.drivers[0].committee.epoch == 0


def test_a_change_governance_did_not_order_does_nothing(cluster):
    bad = change_to(COMMITTEE, signers=SIGNERS[:1])
    assert cluster.drivers[0].propose_epoch_change(bad).broadcasts == ()
    assert cluster.drivers[1].handle_message(wire(encode_epoch_change(bad))).replies == ()
    assert not cluster.drivers[1].replica._store.epoch_is_closed()


def test_a_node_without_governance_never_changes_committee(tmp_path):
    store = SqliteVoteStore(tmp_path / "x.sqlite", COMMITTEE, MEMBERS[0].public_key, create=True)
    replica = QuorumReplica(MEMBERS[0], GENESIS, store, lambda _event: True)
    driver = QuorumDriver(replica)
    change = change_to(COMMITTEE)
    assert driver.propose_epoch_change(change).broadcasts == ()
    assert driver.handle_message(wire(encode_epoch_change(change))).replies == ()
    assert not store.epoch_is_closed()
    store.close()


def test_closure_of_another_epoch_is_ignored(cluster):
    closure = cluster.close_epoch(change_to(COMMITTEE))
    # Installed already: it does not continue the epoch in force any more.
    assert cluster.drivers[1].handle_message(wire(encode_epoch_closure(closure))).replies == ()
    assert cluster.drivers[1].committee.epoch == 1


def test_a_halted_node_takes_no_part(cluster):
    change = change_to(COMMITTEE)
    driver = cluster.drivers[1]
    event_a, event_b = spend(0, "a").transfer, spend(0, "b").transfer
    for event in (event_a, event_b):
        driver.handle_message(
            wire(
                encode_certificate(
                    QuorumCertificate(
                        event,
                        tuple(Vote.create(COMMITTEE, MEMBERS[i], event) for i in range(3)),
                    )
                )
            )
        )
    assert driver.halted
    assert driver.handle_message(wire(encode_epoch_change(change))).replies == ()
    assert driver.propose_epoch_change(change).broadcasts == ()


# --- Locks ------------------------------------------------------------------------------


def _same_members_change():
    return change_to(COMMITTEE, keys=[m.public_key for m in MEMBERS])


def test_a_certified_event_is_in_the_locks_of_any_quorum_of_reports(cluster):
    # Signed by 0, 1, 2. Whichever 3 report, one of the signers is among them.
    signed = spend(0)
    cluster.certify(signed, [0, 1, 2])
    closure = cluster.close_epoch(_same_members_change(), proposer=3, reporters=[3, 1, 0])
    assert closure is not None
    assert signed.transfer.canonical() in {e.canonical() for e in closure.locks()}


def test_the_alternative_of_a_certified_event_gets_no_vote_after_the_closure(cluster):
    signed = spend(0, "first")
    cluster.certify(signed, [0, 1, 2])
    assert cluster.close_epoch(_same_members_change())

    for driver in cluster.drivers:
        output = driver.handle_message(wire(encode_vote_request(spend(0, "second"))))
        assert output.replies == ()


def test_an_unfinished_event_can_finish_in_the_next_epoch(cluster):
    # One vote in the old epoch, and no certificate. The sender sends it again.
    signed = spend(0)
    cluster.drivers[1].handle_message(wire(encode_vote_request(signed)))
    assert cluster.close_epoch(_same_members_change())
    assert all(driver.replica.executed == [] for driver in cluster.drivers)

    cluster.certify(signed, [0, 1, 2])
    assert all(driver.replica.executed == [] for driver in cluster.drivers[1:])
    assert cluster.drivers[0].replica.executed == [signed.transfer]
    certificate = cluster.drivers[0].replica.log[0]
    assert certificate.epoch == 1


def test_equivocation_at_the_end_of_an_epoch_stays_locked_for_good(cluster):
    # The price stated in D2: nobody chooses, and split_lock_ambiguous says nobody can.
    first, second = spend(0, "first"), spend(0, "second")
    cluster.drivers[1].handle_message(wire(encode_vote_request(first)))
    cluster.drivers[2].handle_message(wire(encode_vote_request(second)))
    assert cluster.close_epoch(_same_members_change())

    for driver in cluster.drivers:
        for event in (first, second):
            assert driver.handle_message(wire(encode_vote_request(event))).replies == ()


def test_a_lock_on_one_nonce_leaves_the_next_free(cluster):
    cluster.certify(spend(0), [0, 1, 2])
    assert cluster.close_epoch(_same_members_change())
    assert cluster.drivers[1].handle_message(wire(encode_vote_request(spend(1)))).replies


def test_locks_are_carried_through_several_epochs(cluster):
    signed = spend(0, "first")
    cluster.certify(signed, [0, 1, 2])
    assert cluster.close_epoch(_same_members_change())
    second = change_to(cluster.drivers[0].committee, keys=[m.public_key for m in MEMBERS])
    # Nothing was voted in epoch 1, so the reports are empty: the lock must still hold.
    closure = cluster.close_epoch(second)
    assert closure is not None and closure.locks() == ()
    assert cluster.drivers[0].committee.epoch == 2

    for driver in cluster.drivers:
        output = driver.handle_message(wire(encode_vote_request(spend(0, "second"))))
        assert output.replies == ()


def test_locks_survive_a_restart(tmp_path):
    cluster = Cluster(tmp_path)
    cluster.certify(spend(0, "first"), [0, 1, 2])
    change = _same_members_change()
    assert cluster.close_epoch(change)
    cluster.close()

    store = SqliteVoteStore(
        tmp_path / "a1.sqlite",
        COMMITTEE,
        MEMBERS[1].public_key,
        governance=GOVERNANCE,
    )
    assert store.committee.epoch == 1
    assert not store.record_vote(spend(0, "second").transfer, spend(0, "second"))
    assert store.record_vote(spend(0, "first").transfer, spend(0, "first"))
    store.close()


def test_store_with_epochs_needs_governance_to_open(tmp_path):
    cluster = Cluster(tmp_path)
    assert cluster.close_epoch(_same_members_change())
    cluster.close()
    with pytest.raises(VoteStoreError):
        SqliteVoteStore(tmp_path / "a1.sqlite", COMMITTEE, MEMBERS[1].public_key)


@pytest.mark.parametrize("text", ["nope", '{"change": 1}', "[" * 5_000_000])
def test_store_with_an_unreadable_closure_does_not_open(tmp_path, text):
    import sqlite3

    cluster = Cluster(tmp_path)
    assert cluster.close_epoch(_same_members_change())
    cluster.close()
    path = tmp_path / "a1.sqlite"
    connection = sqlite3.connect(path)
    connection.execute("UPDATE closures SET closure = ?", (text,))
    connection.commit()
    connection.close()

    with pytest.raises(VoteStoreError):
        SqliteVoteStore(path, COMMITTEE, MEMBERS[1].public_key, governance=GOVERNANCE)


def test_store_with_a_closure_that_does_not_verify_does_not_open(tmp_path):
    import sqlite3

    cluster = Cluster(tmp_path)
    assert cluster.close_epoch(_same_members_change())
    cluster.close()
    path = tmp_path / "a1.sqlite"
    connection = sqlite3.connect(path)
    text = connection.execute("SELECT closure FROM closures").fetchone()[0]
    data = json.loads(text)
    data["reports"] = data["reports"][:2]
    connection.execute("UPDATE closures SET closure = ?", (json.dumps(data),))
    connection.commit()
    connection.close()

    with pytest.raises(VoteStoreError):
        SqliteVoteStore(path, COMMITTEE, MEMBERS[1].public_key, governance=GOVERNANCE)


# --- The new committee ------------------------------------------------------------------


def test_old_certificates_stay_valid_after_the_closure(cluster):
    # A node that had not received it yet can still execute it.
    signed = spend(0)
    late = cluster.drivers[3]
    event = signed.transfer
    certificate = QuorumCertificate(
        event,
        tuple(Vote.create(COMMITTEE, MEMBERS[i], event) for i in range(3)),
    )
    for index in (0, 1, 2):
        cluster.drivers[index].handle_message(wire(encode_vote_request(signed)))
    assert cluster.close_epoch(_same_members_change())
    late.handle_message(wire(encode_certificate(certificate)))
    assert late.replica.executed == [event]


def test_certificate_of_an_epoch_this_node_does_not_know_is_ignored(cluster):
    event = spend(0).transfer
    certificate = QuorumCertificate(
        event,
        tuple(Vote.create(COMMITTEE, MEMBERS[i], event) for i in range(3)),
        7,
    )
    driver = cluster.drivers[0]
    driver.handle_message(wire(encode_certificate(certificate)))
    assert driver.replica.executed == []
    assert not driver.halted


def test_old_members_have_no_more_say(tmp_path):
    cluster = Cluster(tmp_path)
    assert cluster.close_epoch(change_to(COMMITTEE))
    event = spend(0).transfer
    old_votes = tuple(Vote.create(COMMITTEE, MEMBERS[i], event) for i in range(3))
    driver = cluster.drivers[0]
    driver.handle_message(wire(encode_certificate(QuorumCertificate(event, old_votes, 1))))
    assert driver.replica.executed == []
    assert driver.handle_message(wire(encode_vote_request(spend(0)))).replies == ()
    cluster.close()


def test_new_members_run_the_new_epoch_and_a_joining_node_catches_up(tmp_path):
    old = Cluster(tmp_path)
    old.certify(spend(0, "bob"), [0, 1, 2])
    old_certificate = old.drivers[0].replica.log[0]
    closure = old.close_epoch(change_to(COMMITTEE))
    assert closure is not None

    joining = [
        old.open(member, COMMITTEE, f"j{index}", joining=True)
        for index, member in enumerate(NEXT_MEMBERS)
    ]

    # What a node that is behind asks, and what any node of the chain answers.
    for driver in joining:
        assert driver.committee.epoch == 0
        replies = old.drivers[0].handle_message(wire(driver.sync_request())).replies
        assert [message["type"] for message in replies] == [
            "EPOCH_CLOSURE",
            "CERTIFICATE_SYNC",
        ]
        for reply in replies:
            driver.handle_message(wire(reply))
        assert driver.committee.epoch == 1
        assert driver.replica.log == [old_certificate]
        assert driver.replica.is_member

    # They hold the lock from the reports of a committee they were not in.
    assert joining[0].handle_message(wire(encode_vote_request(spend(0, "carol")))).replies == ()

    # And they certify and execute by themselves.
    signed = spend(1, "dave")
    output = joining[0].submit(signed)
    assert output.broadcasts
    for index in (1, 2):
        for reply in joining[index].handle_message(wire(encode_vote_request(signed))).replies:
            output = joining[0].handle_message(wire(reply))

    assert joining[0].replica.executed[-1] == signed.transfer
    certificate = output.broadcasts[0]
    assert certificate["epoch"] == 1
    joining[3].handle_message(wire(certificate))
    assert joining[3].replica.executed[-1] == signed.transfer
    assert joining[3].replica.state.root() == StateDeriver.apply_events(
        GENESIS.copy(), joining[3].replica.executed
    ).root()
    old.close()


def test_a_node_two_epochs_behind_gets_both_closures(cluster):
    assert cluster.close_epoch(_same_members_change())
    second = change_to(cluster.drivers[0].committee, keys=[m.public_key for m in MEMBERS])
    assert cluster.close_epoch(second)
    behind = cluster.open(MEMBERS[0], COMMITTEE, "behind")
    replies = cluster.drivers[0].handle_message(wire(behind.sync_request())).replies
    assert [m["type"] for m in replies] == ["EPOCH_CLOSURE", "EPOCH_CLOSURE"]
    for reply in replies:
        behind.handle_message(wire(reply))
    assert behind.committee.epoch == 2


def test_a_request_from_this_epoch_gets_no_closure(cluster):
    assert cluster.close_epoch(_same_members_change())
    request = encode_certificate_sync_request({}, 1)
    assert cluster.drivers[0].handle_message(wire(request)).replies == ()


def test_store_refuses_a_non_member_unless_it_is_joining(tmp_path):
    with pytest.raises(VoteStoreError):
        SqliteVoteStore(tmp_path / "x.sqlite", COMMITTEE, NEXT_MEMBERS[0].public_key, create=True)


# --- Wire forms -------------------------------------------------------------------------


def test_change_round_trip():
    change = change_to(COMMITTEE)
    assert decode_epoch_change(wire(encode_epoch_change(change))) == change


def test_closure_round_trip(cluster):
    closure = cluster.close_epoch(change_to(COMMITTEE))
    assert decode_epoch_closure(wire(encode_epoch_closure(closure))) == closure


@pytest.mark.parametrize(
    "message,decode",
    [
        ({"type": "EPOCH_CHANGE"}, decode_epoch_change),
        ({"type": "EPOCH_CHANGE", "change": 1}, decode_epoch_change),
        ({"type": "EPOCH_REPORT", "change_id": "x", "report": {}}, decode_epoch_report),
        ({"type": "EPOCH_CLOSURE", "closure": {"change": 1, "reports": []}}, decode_epoch_closure),
    ],
)
def test_malformed_epoch_messages_are_value_errors(message, decode):
    with pytest.raises(ValueError):
        decode(message)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda c: c.update(previous="AB" * 32),
        lambda c: c.update(previous=7),
        lambda c: c.update(members="x"),
        lambda c: c.update(members=["ab"]),
        lambda c: c.update(f=-1),
        lambda c: c.update(f=True),
        lambda c: c.update(signatures=[[0]]),
        lambda c: c.update(signatures=[[-1, "ab" * 64]]),
        lambda c: c.update(signatures=[[0, "AB" * 64]]),
        lambda c: c.update(signatures=5),
        lambda c: c.update(extra=1),
    ],
)
def test_malformed_change_is_a_value_error(mutate):
    message = wire(encode_epoch_change(change_to(COMMITTEE)))
    mutate(message["change"])
    with pytest.raises(ValueError):
        decode_epoch_change(message)


# --- Who is to blame --------------------------------------------------------------------


def test_guilty_members_are_those_that_signed_both():
    first = spend(0, "a").transfer
    second = spend(0, "b").transfer
    a = QuorumCertificate(first, tuple(Vote.create(COMMITTEE, MEMBERS[i], first) for i in (0, 1, 2)))
    b = QuorumCertificate(second, tuple(Vote.create(COMMITTEE, MEMBERS[i], second) for i in (1, 2, 3)))
    guilty = guilty_members(COMMITTEE, a, b)
    assert guilty == (MEMBERS[1].public_key, MEMBERS[2].public_key)
    # At least 2q - n, which with n = 3f+1 is f+1: more than the hypothesis allows.
    assert len(guilty) >= 2 * COMMITTEE.quorum - COMMITTEE.n
    assert len(guilty) > COMMITTEE.f


def test_report_signed_with_votes_out_of_order_is_refused():
    # Signed that way by its own validator: one report, one form.
    change_id = change_to(COMMITTEE).change_id
    ordered = _report_for(MEMBERS[0], COMMITTEE, change_id, [spend(0), spend(1)])
    backwards = tuple(reversed(ordered.votes))
    signature = MEMBERS[0].sign(EpochReport._payload(COMMITTEE, change_id, backwards))
    assert not EpochReport(0, backwards, signature).verify(COMMITTEE, change_id)


def test_a_closure_with_a_forged_report_is_not_taken(cluster):
    change = change_to(COMMITTEE)
    reports = [cluster.drivers[i].replica.report_epoch(change) for i in range(3)]
    other = EpochReport(reports[0].validator, reports[0].votes, b"\0" * 64)
    forged = EpochClosure(change, (other, reports[1], reports[2]))
    assert not forged.verify(GOVERNANCE, COMMITTEE)
    cluster.drivers[3].handle_message(wire(encode_epoch_closure(forged)))
    assert cluster.drivers[3].committee.epoch == 0


def test_a_vote_with_no_proof_of_its_sender_stops_the_report(cluster):
    # Reporting without it could lose a certified event.
    replica = cluster.drivers[1].replica
    assert replica.handle_vote_request(spend(0).transfer) is not None
    with pytest.raises(VoteStoreError):
        replica.report_epoch(change_to(COMMITTEE))
    assert not replica._store.epoch_is_closed()
