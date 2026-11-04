"""QuorumDriver: the protocol around the replica, with no network and no Node.

The driver takes messages and returns the messages to send. What a replica does
with an input is compared with the Lean model elsewhere; here is what comes before
it (who may vote, which votes count, when a node halts) and the order of retries.
"""

import random

import pytest

from core.attestation import Committee, QuorumCertificate, Vote
from core.derive import StateDeriver
from core.event import Transfer
from core.signed_event import SignedTransfer
from core.state import State
from crypto.identity import Identity
from network.message import (
    decode_certificate,
    decode_vote,
    decode_vote_request,
    encode_certificate,
    encode_vote,
    encode_vote_request,
)
from network.quorum import (
    QuorumDriver,
    QuorumReplica,
    SqliteVoteStore,
    VoteStoreError,
)

SENDER = Identity.create()
PAYER = SENDER.identity_id
OTHER = Identity.create()
GENESIS = State({PAYER: 10, OTHER.identity_id: 10})
A = Transfer(PAYER, "bob", 8, 0)
B = Transfer(PAYER, "carol", 8, 0)
NEXT = Transfer(PAYER, "bob", 1, 1, (A.event_id(),))
LAST = Transfer(PAYER, "bob", 1, 2, (NEXT.event_id(),))


def signed(event: Transfer, identity: Identity = SENDER) -> SignedTransfer:
    return SignedTransfer.create(identity, event)


def request(event: Transfer, identity: Identity = SENDER) -> dict:
    return encode_vote_request(signed(event, identity))


class Cluster:
    """A committee of real keys and one driver, the node at `index`."""

    def __init__(self, path, f: int = 1, index: int = 0):
        self.path = path
        self.index = index
        self.members = sorted(
            (Identity.create() for _ in range(3 * f + 1)),
            key=lambda identity: identity.public_key,
        )
        self.committee = Committee.create(
            [member.public_key for member in self.members],
            f,
            GENESIS,
        )
        self.create = True
        self.driver = self.open()

    def open(self) -> QuorumDriver:
        identity = self.members[self.index]
        store = SqliteVoteStore(
            self.path,
            self.committee,
            identity.public_key,
            create=self.create,
        )
        self.create = False
        self.store = store
        return QuorumDriver(QuorumReplica(identity, GENESIS, store, lambda _: True))

    def restart(self) -> QuorumDriver:
        self.store.close()
        self.driver = self.open()
        return self.driver

    def vote(self, event: Transfer, index: int) -> Vote:
        return Vote.create(self.committee, self.members[index], event)

    def vote_message(self, event: Transfer, index: int) -> dict:
        return encode_vote(event, self.vote(event, index))

    def certificate(self, event: Transfer, *indexes: int) -> QuorumCertificate:
        return QuorumCertificate(
            event,
            tuple(self.vote(event, index) for index in indexes),
        )

    def certificate_message(self, event: Transfer, *indexes: int) -> dict:
        return encode_certificate(self.certificate(event, *(indexes or (1, 2, 3))))

    def executed(self) -> list[bytes]:
        return [event.canonical() for event in self.driver.replica.executed]

    def voted(self) -> set[bytes]:
        return {event.canonical() for event in self.driver.replica.votes()}


@pytest.fixture
def cluster(tmp_path):
    made = Cluster(tmp_path / "votes.sqlite")
    yield made
    made.store.close()


def nothing(output) -> bool:
    return output.replies == () and output.broadcasts == ()


# --- submit ---------------------------------------------------------------


def test_submit_votes_for_itself_then_asks_the_others(cluster):
    output = cluster.driver.submit(signed(A))

    assert cluster.voted() == {A.canonical()}
    assert output.replies == ()
    assert [decode_vote_request(m).transfer for m in output.broadcasts] == [A]
    assert cluster.executed() == []


def test_submit_with_one_member_certifies_at_once(tmp_path):
    single = Cluster(tmp_path / "single.sqlite", f=0)

    output = single.driver.submit(signed(A))

    assert [decode_certificate(m).event for m in output.broadcasts] == [A]
    assert single.executed() == [A.canonical()]
    single.store.close()


@pytest.mark.parametrize(
    "bad",
    [
        pytest.param(lambda: signed(A, OTHER), id="signed by another identity"),
        pytest.param(
            lambda: SignedTransfer(A, SENDER.public_key, bytes(64)),
            id="invalid signature",
        ),
        pytest.param(
            lambda: signed(Transfer("alias-of-sender", "bob", 1, 0)),
            id="sender is an alias",
        ),
        pytest.param(
            lambda: SignedTransfer(
                Transfer(PAYER, "bob", -1, 0), SENDER.public_key, bytes(64)
            ),
            id="malformed event",
        ),
    ],
)
def test_submit_refuses_what_a_sender_did_not_authorize(cluster, bad):
    assert nothing(cluster.driver.submit(bad()))
    assert cluster.voted() == set()


def test_malformed_event_signed_by_its_sender_leaves_no_trace(cluster):
    # A valid signature on something that is not an event of the model: it must not
    # count as a first version, or a later alternative would look like a proof.
    malformed = Transfer(PAYER, "bob", -1, 0)

    assert nothing(cluster.driver.submit(signed(malformed)))
    assert cluster.driver.submit(signed(A)).broadcasts
    assert cluster.driver.equivocations == {}
    assert cluster.voted() == {A.canonical()}


@pytest.mark.parametrize("amount", [object(), 1.5, "1", None, True, 2**256])
def test_submit_of_a_value_that_is_not_an_event_does_not_raise(cluster, amount):
    event = Transfer(PAYER, "bob", amount, 0)

    assert nothing(
        cluster.driver.submit(SignedTransfer(event, SENDER.public_key, bytes(64)))
    )


def test_submit_of_the_alternative_to_its_own_vote_asks_nobody(cluster):
    cluster.driver.submit(signed(A))

    assert nothing(cluster.driver.submit(signed(B)))
    assert cluster.voted() == {A.canonical()}


def test_submit_again_asks_again_with_the_same_vote(cluster):
    first = cluster.driver.submit(signed(A))
    second = cluster.driver.submit(signed(A))

    assert first.broadcasts == second.broadcasts
    assert len(cluster.voted()) == 1


def test_submit_again_after_a_restart_can_complete_the_certificate(cluster):
    # What was aggregated is lost at a restart, and asking again is the remedy.
    cluster.driver.submit(signed(A))
    cluster.driver.handle_message(cluster.vote_message(A, 1))
    driver = cluster.restart()

    assert nothing(driver.handle_message(cluster.vote_message(A, 2)))
    assert driver.submit(signed(A)).broadcasts
    assert nothing(driver.handle_message(cluster.vote_message(A, 1)))

    output = driver.handle_message(cluster.vote_message(A, 2))
    assert [decode_certificate(m).event for m in output.broadcasts] == [A]


def test_submit_of_an_executed_event_sends_its_certificate(cluster):
    message = cluster.certificate_message(A)
    cluster.driver.handle_message(message)

    output = cluster.driver.submit(signed(A))

    assert output.broadcasts == (message,)
    assert cluster.voted() == set()


# --- VOTE_REQUEST ---------------------------------------------------------


def test_vote_request_is_answered_with_a_valid_vote(cluster):
    output = cluster.driver.handle_message(request(A))

    assert output.broadcasts == ()
    event, vote = decode_vote(output.replies[0])
    assert event == A
    assert vote.verify(cluster.committee, A)
    assert cluster.voted() == {A.canonical()}


def test_vote_request_again_gives_the_same_answer(cluster):
    first = cluster.driver.handle_message(request(A))
    assert cluster.driver.handle_message(request(A)).replies == first.replies


def test_vote_request_with_a_bad_signature_gets_no_answer_and_takes_no_lock(cluster):
    forged = SignedTransfer(A, SENDER.public_key, bytes(64))

    assert nothing(cluster.driver.handle_message(encode_vote_request(forged)))
    assert cluster.voted() == set()
    assert cluster.driver.handle_message(request(B)).replies


def test_vote_request_for_another_sender_gets_no_answer_and_takes_no_lock(cluster):
    assert nothing(cluster.driver.handle_message(request(A, OTHER)))
    assert cluster.voted() == set()
    assert cluster.driver.handle_message(request(B)).replies


def test_vote_request_for_the_alternative_gets_no_answer(cluster):
    cluster.driver.handle_message(request(A))

    assert nothing(cluster.driver.handle_message(request(B)))
    assert cluster.voted() == {A.canonical()}


def test_alternative_signed_by_the_sender_is_kept_as_proof(cluster):
    cluster.driver.handle_message(request(A))
    cluster.driver.handle_message(request(B))

    proof = cluster.driver.equivocations[(PAYER, 0)]
    assert proof.verify()
    assert {proof.first.transfer, proof.second.transfer} == {A, B}


def test_first_proof_of_equivocation_is_kept(cluster):
    third = Transfer(PAYER, "dave", 8, 0)
    cluster.driver.handle_message(request(A))
    cluster.driver.handle_message(request(B))
    proof = cluster.driver.equivocations[(PAYER, 0)]

    cluster.driver.handle_message(request(third))

    assert cluster.driver.equivocations[(PAYER, 0)] == proof


def test_simple_equivocation_does_not_halt_the_node(cluster):
    cluster.driver.handle_message(request(A))
    cluster.driver.handle_message(request(B))

    assert not cluster.driver.halted
    assert cluster.driver.handle_message(request(Transfer(PAYER, "bob", 1, 7))).replies


@pytest.mark.parametrize(
    "second",
    [
        pytest.param(
            lambda: encode_vote_request(SignedTransfer(B, SENDER.public_key, bytes(64))),
            id="forged alternative",
        ),
        pytest.param(lambda: request(A), id="same event"),
        pytest.param(lambda: request(NEXT), id="other nonce"),
    ],
)
def test_no_proof_of_equivocation_without_one(cluster, second):
    cluster.driver.handle_message(request(A))
    cluster.driver.handle_message(second())

    assert cluster.driver.equivocations == {}


def test_failed_write_sends_no_vote(cluster):
    cluster.store._connection.execute("PRAGMA query_only = ON")

    with pytest.raises(VoteStoreError):
        cluster.driver.handle_message(request(A))


# --- VOTE -----------------------------------------------------------------


def test_votes_for_an_event_not_submitted_here_are_ignored(cluster):
    for index in (1, 2, 3):
        assert nothing(cluster.driver.handle_message(cluster.vote_message(A, index)))

    assert cluster.executed() == []


def test_quorum_of_votes_makes_a_certificate_that_is_sent_and_executed(cluster):
    cluster.driver.submit(signed(A))

    assert nothing(cluster.driver.handle_message(cluster.vote_message(A, 1)))
    output = cluster.driver.handle_message(cluster.vote_message(A, 2))

    certificate = decode_certificate(output.broadcasts[0])
    assert certificate.event == A
    assert certificate.verify(cluster.committee)
    assert cluster.executed() == [A.canonical()]


def test_signers_of_a_new_certificate_are_in_order(cluster):
    cluster.driver.submit(signed(A))
    cluster.driver.handle_message(cluster.vote_message(A, 3))
    output = cluster.driver.handle_message(cluster.vote_message(A, 1))

    votes = decode_certificate(output.broadcasts[0]).votes
    assert [vote.validator for vote in votes] == [0, 1, 3]


def test_certificate_is_made_only_once(cluster):
    cluster.driver.submit(signed(A))
    cluster.driver.handle_message(cluster.vote_message(A, 1))
    cluster.driver.handle_message(cluster.vote_message(A, 2))

    assert nothing(cluster.driver.handle_message(cluster.vote_message(A, 3)))
    assert cluster.executed() == [A.canonical()]


def test_same_validator_twice_counts_once(cluster):
    cluster.driver.submit(signed(A))

    assert nothing(cluster.driver.handle_message(cluster.vote_message(A, 1)))
    assert nothing(cluster.driver.handle_message(cluster.vote_message(A, 1)))
    assert cluster.executed() == []


def test_own_vote_sent_back_counts_once(cluster):
    cluster.driver.submit(signed(A))

    assert nothing(cluster.driver.handle_message(cluster.vote_message(A, 0)))
    assert nothing(cluster.driver.handle_message(cluster.vote_message(A, 1)))
    assert cluster.executed() == []


@pytest.mark.parametrize(
    "bad_vote",
    [
        pytest.param(lambda c: Vote(1, bytes(64)), id="invalid signature"),
        pytest.param(lambda c: c.vote(B, 1), id="signature of the alternative"),
        pytest.param(lambda c: Vote(9, c.vote(A, 1).signature), id="beyond the committee"),
        pytest.param(lambda c: Vote(2, c.vote(A, 1).signature), id="signature of another"),
    ],
)
def test_bad_vote_is_dropped_and_does_not_take_the_place_of_a_good_one(cluster, bad_vote):
    cluster.driver.submit(signed(A))

    assert nothing(cluster.driver.handle_message(encode_vote(A, bad_vote(cluster))))
    assert nothing(cluster.driver.handle_message(cluster.vote_message(A, 1)))
    assert cluster.executed() == []
    assert cluster.driver.handle_message(cluster.vote_message(A, 2)).broadcasts


def test_votes_for_the_alternative_do_not_count_for_the_event(cluster):
    cluster.driver.submit(signed(A))

    for index in (1, 2, 3):
        assert nothing(cluster.driver.handle_message(cluster.vote_message(B, index)))

    assert cluster.executed() == []


# --- CERTIFICATE ----------------------------------------------------------


def test_valid_certificate_is_executed_and_sends_nothing(cluster):
    assert nothing(cluster.driver.handle_message(cluster.certificate_message(A)))
    assert cluster.executed() == [A.canonical()]


def test_validator_that_voted_the_alternative_executes_the_certificate(cluster):
    # This is what removes the fork: a vote is a lock, not an execution.
    cluster.driver.handle_message(request(B))

    cluster.driver.handle_message(cluster.certificate_message(A))

    assert cluster.executed() == [A.canonical()]
    assert cluster.voted() == {B.canonical()}
    assert not cluster.driver.halted


def test_execution_does_not_ask_for_the_signature_of_the_sender(cluster):
    # As in the model: the certificate is what authorizes an execution.
    event = Transfer(OTHER.identity_id, "bob", 1, 0)

    cluster.driver.handle_message(cluster.certificate_message(event))

    assert cluster.executed() == [event.canonical()]


def test_same_certificate_twice_runs_once(cluster):
    message = cluster.certificate_message(A)

    cluster.driver.handle_message(message)
    cluster.driver.handle_message(message)

    assert cluster.executed() == [A.canonical()]
    assert not cluster.driver.halted


def test_same_event_with_other_signers_is_not_a_conflict(cluster):
    cluster.driver.handle_message(cluster.certificate_message(A, 1, 2, 3))
    cluster.driver.handle_message(cluster.certificate_message(A, 0, 1, 2))

    assert cluster.executed() == [A.canonical()]
    assert not cluster.driver.halted


def test_certificate_with_its_parent_missing_waits_and_runs_later(cluster):
    cluster.driver.handle_message(cluster.certificate_message(NEXT))
    assert cluster.executed() == []

    cluster.driver.handle_message(cluster.certificate_message(A))
    assert cluster.executed() == [A.canonical(), NEXT.canonical()]


def test_chain_in_reverse_order_runs_to_the_fixed_point(cluster):
    cluster.driver.handle_message(cluster.certificate_message(LAST))
    cluster.driver.handle_message(cluster.certificate_message(NEXT))
    assert cluster.executed() == []

    cluster.driver.handle_message(cluster.certificate_message(A))

    assert cluster.executed() == [A.canonical(), NEXT.canonical(), LAST.canonical()]


def test_certificates_ready_together_run_in_order_of_id(cluster):
    # Two senders, because for one the nonce already fixes the order. The keys are
    # random, so the parent is chosen with an id below both: in the pass that runs
    # the parent, a child with a lower id was already skipped and runs after one
    # with a higher id.
    for attempt in range(1000):
        parent = Transfer(PAYER, f"bob-{attempt}", 8, 0)
        children = sorted(
            (
                Transfer(PAYER, "bob", 1, 1, (parent.event_id(),)),
                Transfer(OTHER.identity_id, "bob", 1, 0, (parent.event_id(),)),
            ),
            key=lambda event: event.event_id(),
        )
        if parent.event_id() < children[0].event_id():
            break

    for child in reversed(children):
        cluster.driver.handle_message(cluster.certificate_message(child))
    cluster.driver.handle_message(cluster.certificate_message(parent))

    assert cluster.executed() == [
        event.canonical() for event in [parent, *children]
    ]


def test_certificate_stays_waiting_after_a_failed_write(cluster):
    cluster.driver.handle_message(cluster.certificate_message(NEXT))
    cluster.store._connection.execute("PRAGMA query_only = ON")

    with pytest.raises(VoteStoreError):
        cluster.driver.handle_message(cluster.certificate_message(A))
    assert cluster.executed() == []

    cluster.store._connection.execute("PRAGMA query_only = OFF")
    cluster.driver.handle_message(cluster.certificate_message(A))

    assert cluster.executed() == [A.canonical(), NEXT.canonical()]


def test_certificate_without_funds_waits_for_the_funds(cluster):
    payer = OTHER.identity_id
    spend = Transfer(payer, "dave", 15, 0)
    fund = Transfer(PAYER, payer, 8, 0)

    cluster.driver.handle_message(cluster.certificate_message(spend))
    assert cluster.executed() == []

    cluster.driver.handle_message(cluster.certificate_message(fund))
    assert cluster.executed() == [fund.canonical(), spend.canonical()]


def _invalid_certificates(cluster, event):
    good = cluster.certificate(event, 1, 2, 3)
    return {
        "bad signature": QuorumCertificate(
            event, (Vote(1, bytes(64)),) + good.votes[1:]
        ),
        "below quorum": cluster.certificate(event, 1, 2),
        "repeated signer": QuorumCertificate(event, good.votes[:2] + good.votes[:1]),
        "signatures of the other event": QuorumCertificate(
            event, cluster.certificate(A if event != A else B, 1, 2, 3).votes
        ),
        "beyond the committee": QuorumCertificate(
            event, good.votes[:2] + (Vote(9, bytes(64)),)
        ),
    }


INVALID = [
    "bad signature",
    "below quorum",
    "repeated signer",
    "signatures of the other event",
    "beyond the committee",
]


@pytest.mark.parametrize("kind", INVALID)
def test_invalid_certificate_is_dropped(cluster, kind):
    invalid = _invalid_certificates(cluster, A)[kind]

    assert nothing(cluster.driver.handle_message(encode_certificate(invalid)))

    assert cluster.executed() == []
    assert not cluster.driver.halted
    # It left nothing behind that could take the place of the valid one.
    cluster.driver.handle_message(cluster.certificate_message(A))
    assert cluster.executed() == [A.canonical()]


@pytest.mark.parametrize("kind", INVALID)
def test_invalid_certificate_in_conflict_never_halts_the_node(cluster, kind):
    # Otherwise one message from anyone would stop a node for good.
    cluster.driver.handle_message(cluster.certificate_message(A))

    invalid = _invalid_certificates(cluster, B)[kind]
    cluster.driver.handle_message(encode_certificate(invalid))

    assert not cluster.driver.halted
    assert cluster.driver.replica.state.balance("bob") == 8


# --- Halting --------------------------------------------------------------


def _assert_halted_on_a_and_b(cluster) -> None:
    assert cluster.driver.halted
    assert cluster.store.halted()
    assert {c.event for c in cluster.store.halt_proof()} == {A, B}


def test_conflict_with_the_log_halts_and_keeps_the_state(cluster):
    cluster.driver.handle_message(cluster.certificate_message(A))
    root = cluster.driver.replica.state.root()

    assert nothing(cluster.driver.handle_message(cluster.certificate_message(B)))

    _assert_halted_on_a_and_b(cluster)
    assert cluster.executed() == [A.canonical()]
    assert cluster.driver.replica.state.root() == root


def test_conflict_with_the_buffer_halts_before_any_execution(cluster):
    child_a = Transfer(PAYER, "bob", 8, 0, ("ab" * 32,))
    child_b = Transfer(PAYER, "carol", 8, 0, ("ab" * 32,))
    cluster.driver.handle_message(cluster.certificate_message(child_a))
    assert cluster.executed() == []

    cluster.driver.handle_message(cluster.certificate_message(child_b))

    assert cluster.driver.halted
    assert {c.event for c in cluster.store.halt_proof()} == {child_a, child_b}
    assert cluster.executed() == []


def test_failed_write_of_the_halt_leaves_the_error_visible(cluster):
    cluster.driver.handle_message(cluster.certificate_message(A))
    cluster.store._connection.execute("PRAGMA query_only = ON")

    with pytest.raises(VoteStoreError):
        cluster.driver.handle_message(cluster.certificate_message(B))

    assert not cluster.driver.halted


def _halt(cluster) -> None:
    cluster.driver.handle_message(cluster.certificate_message(A))
    cluster.driver.handle_message(cluster.certificate_message(B))
    assert cluster.driver.halted


def test_halted_node_answers_nothing_and_changes_nothing(cluster):
    _halt(cluster)
    voted = cluster.voted()
    executed = cluster.executed()
    later = Transfer(OTHER.identity_id, "bob", 1, 0)

    for message in (
        request(later, OTHER),
        cluster.vote_message(later, 1),
        cluster.certificate_message(later),
    ):
        assert nothing(cluster.driver.handle_message(message))

    assert nothing(cluster.driver.submit(signed(later, OTHER)))
    assert cluster.voted() == voted
    assert cluster.executed() == executed
    # It keeps nothing in memory for what can never run.
    assert cluster.driver._buffer == {}
    assert cluster.driver._aggregating == {}


def test_halted_node_does_not_send_a_certificate_it_holds(cluster):
    _halt(cluster)

    assert nothing(cluster.driver.submit(signed(A)))


def test_buffered_certificate_does_not_run_after_a_halt(cluster):
    waiting = Transfer(OTHER.identity_id, "dave", 15, 0)
    cluster.driver.handle_message(cluster.certificate_message(waiting))

    _halt(cluster)

    # These would pay for it, if the node still executed.
    funding = Transfer(PAYER, OTHER.identity_id, 1, 1, (A.event_id(),))
    cluster.driver.handle_message(cluster.certificate_message(funding))
    assert waiting.canonical() not in cluster.executed()
    assert cluster.driver._buffer == {}


def test_votes_being_collected_make_no_certificate_after_a_halt(cluster):
    later = Transfer(OTHER.identity_id, "bob", 1, 0)
    cluster.driver.submit(signed(later, OTHER))
    cluster.driver.handle_message(cluster.vote_message(later, 1))

    _halt(cluster)

    assert nothing(cluster.driver.handle_message(cluster.vote_message(later, 2)))


def test_halt_survives_a_restart(cluster):
    _halt(cluster)

    driver = cluster.restart()

    assert driver.halted
    assert nothing(driver.handle_message(request(NEXT)))
    assert nothing(driver.handle_message(cluster.certificate_message(NEXT)))
    assert cluster.executed() == [A.canonical()]


def test_conflict_with_the_log_is_seen_after_a_restart(cluster):
    cluster.driver.handle_message(cluster.certificate_message(A))

    driver = cluster.restart()
    driver.handle_message(cluster.certificate_message(B))

    _assert_halted_on_a_and_b(cluster)


def test_executed_event_survives_a_restart_without_running_again(cluster):
    message = cluster.certificate_message(A)
    cluster.driver.handle_message(message)

    driver = cluster.restart()
    driver.handle_message(message)

    assert cluster.executed() == [A.canonical()]


# --- Messages -------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        {"type": "VOTE_REQUEST"},
        {"type": "VOTE", "transfer": {}, "validator": 0, "signature": "zz"},
        {"type": "CERTIFICATE", "transfer": 1, "votes": []},
        {"type": "SOMETHING_ELSE"},
        {},
    ],
)
def test_malformed_message_raises_value_error(cluster, message):
    # The connection is closed for this, and it does not stop the node.
    with pytest.raises(ValueError):
        cluster.driver.handle_message(message)

    assert not cluster.driver.halted


# --- The result depends on the set, not on the order of arrival -----------


def _spends(rng):
    """Chains of two senders, where one funds the other, with some out of funds."""
    payer, second = PAYER, OTHER.identity_id
    events = []
    parent = ()

    for nonce in range(rng.randint(2, 5)):
        event = Transfer(payer, second, rng.randint(1, 3), nonce, parent)
        events.append(event)
        parent = (event.event_id(),)

    parent = ()
    for nonce in range(rng.randint(2, 5)):
        event = Transfer(second, "bob", rng.randint(1, 6), nonce, parent)
        events.append(event)
        parent = (event.event_id(),)

    return events


@pytest.mark.parametrize("seed", range(8))
def test_any_order_of_arrival_gives_the_same_state_and_set(tmp_path, seed):
    rng = random.Random(seed)
    events = _spends(rng)
    results = set()

    first = Cluster(tmp_path / "base.sqlite")
    messages = [first.certificate_message(event) for event in events]
    first.store.close()

    for attempt in range(6):
        order = list(messages)
        rng.shuffle(order)
        path = tmp_path / f"run-{attempt}.sqlite"
        store = SqliteVoteStore(
            path,
            first.committee,
            first.members[0].public_key,
            create=True,
        )
        driver = QuorumDriver(
            QuorumReplica(first.members[0], GENESIS, store, lambda _: True)
        )
        for message in order:
            driver.handle_message(message)

        results.add(
            (
                driver.replica.state.root(),
                frozenset(event.canonical() for event in driver.replica.executed),
            )
        )
        assert not driver.halted

        # The log is a valid execution: state is what derive gives for it.
        assert (
            StateDeriver.apply_events(GENESIS.copy(), driver.replica.executed).root()
            == driver.replica.state.root()
        )
        store.close()

    assert len(results) == 1
