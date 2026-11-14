"""Node in quorum mode: how the rules of network/quorum/ meet the network.

The rules themselves are tested in test_quorum_driver.py. With quorum=None the node
must not change at all, and for that the proof is that the existing tests of Node
pass unmodified.
"""

import json
import sqlite3
import threading
from pathlib import Path

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
    encode_signed_transfer,
    encode_vote,
    encode_vote_request,
)
from network.node import Node
from network.peer import Peer
from network.peer_connection import PeerConnection
from network.quorum import QuorumConfig, VoteStoreError
from tests.test_peer_connection_receive_loop import FakeSocket

SENDER = Identity.create()
PAYER = SENDER.identity_id
GENESIS = State({PAYER: 10})
A = Transfer(PAYER, "bob", 8, 0)
B = Transfer(PAYER, "carol", 8, 0)
NEXT = Transfer(PAYER, "bob", 1, 1, (A.event_id(),))


def signed(event: Transfer) -> SignedTransfer:
    return SignedTransfer.create(SENDER, event)


class Committee4:
    """Real keys for n = 4, f = 1, and files for each member."""

    def __init__(self, directory: Path):
        self.directory = directory
        self.members = sorted(
            (Identity.create() for _ in range(4)),
            key=lambda identity: identity.public_key,
        )
        self.committee = Committee.create(
            [member.public_key for member in self.members],
            1,
            GENESIS,
        )
        self.created = set()
        self.nodes = []

    def config(self, index: int = 0) -> QuorumConfig:
        create = index not in self.created
        self.created.add(index)
        return QuorumConfig(
            self.committee,
            self.members[index],
            self.directory / f"votes-{index}.sqlite",
            create=create,
        )

    def node(self, index: int = 0, name: str | None = None) -> Node:
        node = Node(name or f"q-{index}", GENESIS, quorum=self.config(index))
        self.nodes.append(node)
        return node

    def certificate(self, event: Transfer, *indexes: int) -> QuorumCertificate:
        return QuorumCertificate(
            event,
            tuple(
                Vote.create(self.committee, self.members[index], event)
                for index in (indexes or (0, 1, 2, 3))
            ),
        )

    def stop_all(self) -> None:
        for node in self.nodes:
            node.stop()


@pytest.fixture
def four(tmp_path):
    made = Committee4(tmp_path)
    yield made
    made.stop_all()


def drive(node: Node, *events: Transfer, four: Committee4) -> None:
    """Execute events on the runtime directly, as later commits do from messages."""
    for event in events:
        node._quorum.driver.handle_message(
            encode_certificate(four.certificate(event))
        )
    with node._state_lock:
        node._publish_quorum_state()


# --- Without a quorum configuration ---------------------------------------


@pytest.mark.parametrize("arguments", [{}, {"quorum": None}], ids=["missing", "None"])
def test_node_without_quorum_is_refused(tmp_path, monkeypatch, arguments):
    monkeypatch.chdir(tmp_path)

    with pytest.raises(TypeError):
        Node("plain", State({"alice": 10}), **arguments)

    assert list(tmp_path.glob("*.sqlite*")) == []


# --- Starting -------------------------------------------------------------


def test_wrong_genesis_is_refused_by_the_constructor(four):
    with pytest.raises(ValueError):
        Node("q-wrong", State({PAYER: 11}), quorum=four.config())

    assert not (four.directory / "votes-0.sqlite").exists()


def test_node_without_initial_state_is_refused(four):
    with pytest.raises(ValueError):
        Node("q-none", quorum=four.config())


def test_new_node_publishes_the_genesis(four):
    node = four.node()

    assert node.state.root() == GENESIS.root()
    assert node.events == []
    assert node.local_events == []


def test_second_node_on_the_same_file_is_refused(four):
    four.node()

    with pytest.raises(VoteStoreError):
        Node("q-other", GENESIS, quorum=four.config())


def test_stop_releases_the_file_for_a_new_node(four):
    four.node().stop()

    four.node()


def test_stop_twice_is_harmless(four):
    node = four.node()
    node.stop()
    node.stop()


def test_stopped_node_does_not_start_again(four):
    # The store is closed, and a new node is what recovers from the log.
    node = four.node()
    node.stop()

    with pytest.raises(RuntimeError):
        node.start()


def test_stop_and_start_work_on_a_running_node(four):
    node = four.node()
    node.start()
    assert node.address()[1] != 0
    node.stop()
    assert node._quorum.closed


# --- Public state ---------------------------------------------------------


def test_public_state_matches_derive_on_the_log(four):
    node = four.node()

    drive(node, A, NEXT, four=four)

    assert node.local_events == [A, NEXT]
    assert node.events == node.local_events
    assert (
        StateDeriver.apply_events(GENESIS.copy(), node.local_events).root()
        == node.state.root()
    )


def test_public_state_is_a_copy(four):
    node = four.node()
    drive(node, A, four=four)
    root = node._quorum.replica.state.root()

    node.state.balances["mallory"] = 1000
    node.local_events.clear()
    node.events.clear()

    assert node._quorum.replica.state.root() == root
    assert len(node._quorum.replica.executed) == 1


def test_restart_brings_back_state_and_log(four):
    node = four.node()
    drive(node, A, NEXT, four=four)
    root = node.state.root()
    node.stop()

    again = four.node()

    assert again.state.root() == root
    assert again.local_events == [A, NEXT]
    assert again.events == [A, NEXT]


def test_restart_does_not_bring_back_evidence(four):
    # A known limit: evidence is in memory, the votes and the log are on disk.
    node = four.node()
    node._quorum.driver.handle_message(encode_vote_request(signed(A)))
    with node._state_lock:
        node._publish_quorum_state()
    assert node.signed_events
    node.stop()

    again = four.node()

    assert again.signed_events == {}
    assert again._quorum.replica.votes() == [A]


def test_evidence_and_equivocation_are_published(four):
    node = four.node()

    for event in (A, B):
        node._quorum.driver.handle_message(encode_vote_request(signed(event)))
    with node._state_lock:
        node._publish_quorum_state()

    assert set(node.signed_events) == {A.event_id(), B.event_id()}
    assert len(node.equivocations.proofs) == 1
    assert node.equivocations.proofs[0].verify()
    # Evidence is not knowledge: nothing here counts as an event of the node.
    assert node.events == []


def test_stop_waits_for_a_message_being_handled(four):
    node = four.node()
    entered = threading.Event()
    finished = threading.Event()

    def holder():
        with node._state_lock:
            entered.set()
            finished.wait(timeout=5)

    thread = threading.Thread(target=holder, daemon=True)
    thread.start()
    assert entered.wait(timeout=5)
    stopper = threading.Thread(target=node.stop, daemon=True)
    stopper.start()
    stopper.join(timeout=0.3)
    assert stopper.is_alive()

    finished.set()
    stopper.join(timeout=5)
    thread.join(timeout=5)
    assert not stopper.is_alive()
    assert node._quorum.closed


# --- Messages outside the protocol and evidence ---------------------------


def _assert_nothing_executed(node) -> None:
    assert node.state.root() == GENESIS.root()
    assert node.events == []
    assert node.local_events == []
    assert node._quorum.replica.executed == []
    assert node._quorum.replica.votes() == []


@pytest.mark.parametrize(
    "historical",
    ["receive", "merge_events", "signed_event_lifecycle", "status", "decision_context",
     "register_identity_claim", "sync_with", "send_signed_transfer"],
)
def test_historical_entries_are_gone(four, historical):
    assert not hasattr(four.node(), historical)


def test_receive_signed_keeps_evidence_and_executes_nothing(four):
    node = four.node()

    assert node.receive_signed(signed(A)) is False

    assert set(node.signed_events) == {A.event_id()}
    _assert_nothing_executed(node)


def test_receive_signed_of_an_invalid_event_keeps_nothing(four):
    node = four.node()

    assert node.receive_signed(SignedTransfer(A, SENDER.public_key, bytes(64))) is False

    assert node.signed_events == {}
    _assert_nothing_executed(node)


def _signed_wire(event: SignedTransfer) -> dict:
    data = encode_signed_transfer(event)
    return {
        "transfer": data["transfer"],
        "public_key": data["public_key"],
        "signature": data["signature"],
    }


@pytest.mark.parametrize(
    "message",
    [
        pytest.param(lambda: encode_signed_transfer(signed(A)), id="SIGNED_TRANSFER"),
        pytest.param(
            lambda: {"type": "SIGNED_EVENT_SYNC", "events": [_signed_wire(signed(A))]},
            id="SIGNED_EVENT_SYNC",
        ),
        pytest.param(
            lambda: {"type": "KNOWLEDGE_RESPONSE", "identities": [], "events": [_signed_wire(signed(A))]},
            id="KNOWLEDGE_RESPONSE",
        ),
        pytest.param(lambda: {"type": "IDENTITY_CLAIM", "alias": "alice"}, id="IDENTITY_CLAIM"),
        pytest.param(lambda: {"type": "EVENT_SYNC", "events": []}, id="EVENT_SYNC"),
        pytest.param(lambda: {"type": "DECISION_CONTEXT", "status": "UNIQUE"}, id="DECISION_CONTEXT"),
        pytest.param(lambda: {"type": 7}, id="type not a string"),
    ],
)
def test_message_outside_the_protocol_is_dropped(four, message):
    node = four.node()
    connection = FakeConnection()

    node._handle_peer_message(message(), connection)

    assert connection.sent == []
    assert not connection.closed
    assert node.signed_events == {}
    _assert_nothing_executed(node)


def test_two_versions_received_make_a_proof_and_no_fork(four):
    node = four.node()

    node.receive_signed(signed(A))
    node.receive_signed(signed(B))

    assert len(node.equivocations.proofs) == 1
    _assert_nothing_executed(node)
    assert not node.conflicted


# --- Messages -------------------------------------------------------------


class FakeConnection:
    """Records what is sent, and can run a check while a send is in progress."""

    def __init__(self, during_send=None, fails: bool = False):
        self.sent: list[dict] = []
        self.during_send = during_send
        self.fails = fails
        self.closed = False
        self.initiated_locally = True

    @property
    def connected(self) -> bool:
        return not self.closed

    def send(self, message: dict) -> None:
        if self.during_send is not None:
            self.during_send()
        if self.fails:
            raise OSError("broken pipe")
        # What a real connection does to a message.
        self.sent.append(json.loads(json.dumps(message)))

    def enqueue(self, message):

        self.send(message)

        return 0


    def charge(self, tokens):

        pass

    def close(self) -> None:
        self.closed = True


def _attach(node: Node, name: str, connection=None) -> FakeConnection:
    connection = connection or FakeConnection()
    node.peers[name] = Peer(node_id=name, host="127.0.0.1", port=1)
    node.peer_connections[name] = connection
    return connection


def test_vote_request_is_answered_on_its_own_connection(four):
    node = four.node()
    asker = FakeConnection()
    bystander = _attach(node, "bystander")

    node._handle_peer_message(encode_vote_request(signed(A)), asker)

    event, vote = decode_vote(asker.sent[0])
    assert event == A
    assert vote.verify(four.committee, A)
    assert bystander.sent == []
    assert node.state.root() == GENESIS.root()


def test_every_vote_that_leaves_is_on_disk_first(four):
    node = four.node()
    seen = []

    def on_send():
        # A separate connection: what would survive a crash at this moment.
        connection = sqlite3.connect(four.directory / "votes-0.sqlite")
        seen.append(connection.execute("SELECT canonical FROM votes").fetchall())
        connection.close()

    node._handle_peer_message(
        encode_vote_request(signed(A)),
        FakeConnection(during_send=on_send),
    )

    assert seen == [[(A.canonical().decode(),)]]


def test_certificate_message_executes_and_publishes(four):
    node = four.node()

    node._handle_peer_message(encode_certificate(four.certificate(A)))

    assert node.local_events == [A]
    assert node.events == [A]
    assert node.state.balance("bob") == 8


def test_validator_that_voted_the_alternative_executes_the_certificate(four):
    # The test of this whole work, for one node: voted for b, executes a.
    node = four.node()
    node._handle_peer_message(encode_vote_request(signed(B)), FakeConnection())

    node._handle_peer_message(encode_certificate(four.certificate(A)))

    assert node.local_events == [A]
    assert node.state.balance("carol") == 0


def test_invalid_certificate_changes_nothing(four):
    node = four.node()
    good = four.certificate(A)
    forged = QuorumCertificate(A, (Vote(1, bytes(64)),) + good.votes[1:])

    node._handle_peer_message(encode_certificate(forged))

    _assert_nothing_executed(node)


@pytest.mark.parametrize(
    "message",
    [
        {"type": "VOTE_REQUEST"},
        {"type": "VOTE", "transfer": 1, "validator": 0, "signature": ""},
        {"type": "CERTIFICATE", "transfer": {}, "votes": []},
    ],
)
def test_malformed_message_closes_only_that_connection(four, message):
    node = four.node()
    peer = PeerConnection("q-0", "127.0.0.1", 1)
    peer.connection = FakeSocket()
    messages = [message]
    peer.receive = lambda: messages.pop()

    peer.receive_loop(node._handle_peer_message)

    assert peer.connection is None
    node._handle_peer_message(encode_certificate(four.certificate(A)))
    assert node.local_events == [A]


def test_submit_votes_then_asks_every_peer(four):
    node = four.node()
    first, second = _attach(node, "peer-1"), _attach(node, "peer-2")

    assert node.submit(signed(A))

    for peer in (first, second):
        assert [decode_vote_request(m).transfer for m in peer.sent] == [A]
    assert node._quorum.replica.votes() == [A]
    assert node.local_events == []


def test_submit_refused_returns_false_and_sends_nothing(four):
    node = four.node()
    peer = _attach(node, "peer-1")

    assert not node.submit(SignedTransfer(A, SENDER.public_key, bytes(64)))

    assert peer.sent == []


def test_quorum_of_votes_sends_the_certificate_to_every_peer(four):
    node = four.node()
    first, second = _attach(node, "peer-1"), _attach(node, "peer-2")
    node.submit(signed(A))

    for index in (1, 2, 3):
        node._handle_peer_message(
            encode_vote(A, Vote.create(four.committee, four.members[index], A))
        )

    # The prepare certificate, this node's precommit, then the decision of all four votes.
    for peer in (first, second):
        certificates = [decode_certificate(m) for m in peer.sent if m["type"] == "CERTIFICATE"]
        assert [c.event for c in certificates] == [A, A]
        assert certificates[-1].decides(four.committee)
    assert node.local_events == [A]


def _lock_is_free(node: Node) -> bool:
    """From another thread, since the lock is reentrant for the one that holds it."""
    result = []

    def attempt():
        acquired = node._state_lock.acquire(timeout=0.5)
        result.append(acquired)
        if acquired:
            node._state_lock.release()

    thread = threading.Thread(target=attempt)
    thread.start()
    thread.join()
    return result[0]


def test_no_send_happens_with_the_state_lock_held(four):
    node = four.node()
    seen = []
    during = lambda: seen.append(_lock_is_free(node))  # noqa: E731

    # A reply.
    node._handle_peer_message(
        encode_vote_request(signed(A)),
        FakeConnection(during_send=during),
    )
    # A broadcast from submit.
    _attach(node, "peer-1", FakeConnection(during_send=during))
    other = Transfer(PAYER, "bob", 1, 1, (A.event_id(),))
    node.submit(signed(other))
    # A broadcast from a quorum of votes.
    for index in (1, 2):
        node._handle_peer_message(
            encode_vote(other, Vote.create(four.committee, four.members[index], other))
        )

    # The reply, the request, then the prepare certificate and the precommit.
    assert seen and all(seen)


def test_peer_that_does_not_read_does_not_block_the_node(four):
    node = four.node()
    entered, release = threading.Event(), threading.Event()

    def block():
        entered.set()
        release.wait(timeout=5)

    _attach(node, "stuck", FakeConnection(during_send=block))
    thread = threading.Thread(target=node.submit, args=(signed(A),), daemon=True)
    thread.start()
    assert entered.wait(timeout=5)

    node._handle_peer_message(encode_certificate(four.certificate(A)))
    assert node.local_events == [A]

    release.set()
    thread.join(timeout=5)


def test_failed_broadcast_drops_that_peer_and_reaches_the_others(four):
    node = four.node()
    broken = _attach(node, "broken", FakeConnection(fails=True))
    healthy = _attach(node, "healthy")

    node.submit(signed(A))

    assert broken.closed
    assert "broken" not in node.peer_connections
    assert "broken" in node.peers
    assert len(healthy.sent) == 1


def test_failed_reply_closes_that_connection_and_does_not_raise(four):
    node = four.node()
    broken = _attach(node, "broken", FakeConnection(fails=True))

    node._handle_peer_message(encode_vote_request(signed(A)), broken)

    assert broken.closed
    assert "broken" not in node.peer_connections
    # The vote stays, and asking again gives the same one.
    assert node._quorum.replica.votes() == [A]


def test_message_after_stop_is_ignored(four):
    node = four.node()
    node.stop()

    node._handle_peer_message(encode_vote_request(signed(A)), FakeConnection())
    node._handle_peer_message(encode_certificate(four.certificate(A)))

    assert node.local_events == []


def test_messages_from_many_threads_are_serialized(four):
    # The replica is not thread-safe: Node has to serialize the calls. Certificates
    # of a chain and vote requests, repeated, from threads that start together.
    node = four.node()
    chain = [A]
    for nonce in (1, 2):
        chain.append(Transfer(PAYER, "bob", 1, nonce, (chain[-1].event_id(),)))
    messages = [encode_certificate(four.certificate(event)) for event in chain]
    messages += [encode_vote_request(signed(event)) for event in chain]
    barrier = threading.Barrier(8)
    errors = []

    def worker(offset):
        try:
            barrier.wait(timeout=5)
            for index in range(len(messages)):
                message = messages[(index + offset) % len(messages)]
                node._handle_peer_message(message, FakeConnection())
        except Exception as error:
            errors.append(error)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert errors == []
    assert node.local_events == chain
    assert (
        StateDeriver.apply_events(GENESIS.copy(), node.local_events).root()
        == node.state.root()
    )


def test_state_is_published_even_when_a_later_write_fails(four, monkeypatch):
    # The buffer runs A and then fails on NEXT. A did execute, and is on disk: the
    # public state must not stay behind until some other message arrives.
    node = four.node()
    node._handle_peer_message(encode_certificate(four.certificate(NEXT)))
    store = node._quorum.replica._store
    real = store.append_certificate

    def fail_on_next(certificate):
        if certificate.event == NEXT:
            raise VoteStoreError("disk full")
        real(certificate)

    monkeypatch.setattr(store, "append_certificate", fail_on_next)

    with pytest.raises(VoteStoreError):
        node._handle_peer_message(encode_certificate(four.certificate(A)))

    assert node.local_events == [A]
    assert node.state.balance("bob") == 8


def test_driver_runs_with_the_state_lock_held(four, monkeypatch):
    # The test above depends on timing. This one does not.
    node = four.node()
    seen = []
    real_handle = node._quorum.driver.handle_message
    real_submit = node._quorum.driver.submit

    def handle(message):
        seen.append(_lock_is_free(node))
        return real_handle(message)

    def submit(event):
        seen.append(_lock_is_free(node))
        return real_submit(event)

    monkeypatch.setattr(node._quorum.driver, "handle_message", handle)
    monkeypatch.setattr(node._quorum.driver, "submit", submit)

    node._handle_peer_message(encode_vote_request(signed(A)), FakeConnection())
    node.submit(signed(A))

    assert seen == [False, False]


# --- Halting and errors of the disk ---------------------------------------


def _halt(node: Node, four: Committee4) -> None:
    for event in (A, B):
        node._handle_peer_message(encode_certificate(four.certificate(event)))


def test_status_is_not_conflicted_for_a_node_that_runs(four):
    node = four.node()
    node._handle_peer_message(encode_certificate(four.certificate(A)))

    assert not node.conflicted


def test_status_is_not_conflicted_for_a_simple_equivocation(four):
    node = four.node()

    for event in (A, B):
        node._handle_peer_message(encode_vote_request(signed(event)), FakeConnection())

    assert len(node.equivocations.proofs) == 1
    assert not node.conflicted


def test_two_valid_certificates_in_conflict_stop_the_node(four):
    node = four.node()
    node._handle_peer_message(encode_certificate(four.certificate(A)))
    root = node.state.root()

    node._handle_peer_message(encode_certificate(four.certificate(B)))

    assert node.conflicted
    assert node.state.root() == root
    assert node.local_events == [A]
    # No winner: the alternative is proof, and it did not enter the log.
    assert B not in node.events


def test_forged_certificate_in_conflict_does_not_stop_the_node(four):
    node = four.node()
    node._handle_peer_message(encode_certificate(four.certificate(A)))
    good = four.certificate(B)
    forged = QuorumCertificate(B, (Vote(1, bytes(64)),) + good.votes[1:])

    node._handle_peer_message(encode_certificate(forged))

    assert not node.conflicted
    assert node._handle_peer_message(encode_vote_request(signed(NEXT))) is None
    assert node._quorum.replica.votes() == [NEXT]


def test_halted_node_signs_nothing_and_executes_nothing(four):
    node = four.node()
    _halt(node, four)
    asker = FakeConnection()

    node._handle_peer_message(encode_vote_request(signed(NEXT)), asker)
    node._handle_peer_message(encode_certificate(four.certificate(NEXT)))

    assert asker.sent == []
    assert not node.submit(signed(NEXT))
    assert node.local_events == [A]


def test_halt_survives_a_restart_of_the_node(four):
    node = four.node()
    _halt(node, four)
    node.stop()

    again = four.node()

    assert again.conflicted
    assert again.local_events == [A]
    asker = FakeConnection()
    again._handle_peer_message(encode_vote_request(signed(NEXT)), asker)
    assert asker.sent == []


def test_status_still_answers_after_stop(four):
    node = four.node()
    _halt(node, four)
    node.stop()

    assert node.conflicted


def test_evidence_after_stop_does_not_touch_the_closed_store(four):
    # A message of the old kind can still be in flight when the node stops.
    node = four.node()
    node.stop()

    assert node.receive_signed(signed(A)) is False

    assert set(node.signed_events) == {A.event_id()}


def test_failed_write_closes_the_connection_and_signs_nothing(four):
    node = four.node()
    store = node._quorum.replica._store
    store._connection.execute("PRAGMA query_only = ON")
    sock = FakeSocket()
    sent = []
    sock.sendall = sent.append
    peer = PeerConnection("q-0", "127.0.0.1", 1)
    peer.connection = sock
    messages = [encode_vote_request(signed(A))]
    peer.receive = lambda: messages.pop()
    gone = []
    peer.on_disconnect = gone.append

    # receive_loop closes the connection and raises it again: a disk that fails
    # must be seen, and must not look like a malformed message.
    with pytest.raises(VoteStoreError):
        peer.receive_loop(node._handle_peer_message)

    assert peer.connection is None
    assert gone == [peer]
    assert sent == []


def test_failed_submit_raises_and_asks_nobody(four):
    node = four.node()
    peer = _attach(node, "peer-1")
    node._quorum.replica._store._connection.execute("PRAGMA query_only = ON")

    with pytest.raises(VoteStoreError):
        node.submit(signed(A))

    assert peer.sent == []


# --- Four nodes through encoded messages ----------------------------------


class Network:
    """Delivers encoded messages between real Nodes, one at a time, with no sockets."""

    def __init__(self, nodes: list[Node]):
        self.nodes = nodes
        self.queue: list[tuple[Node, dict, "Link"]] = []
        for node in nodes:
            for other in nodes:
                if other is not node:
                    node.peer_connections[other.node_id] = Link(self, other, node)

    def run(self, deliver=lambda destination, message: True) -> None:
        while self.queue:
            destination, message, reply = self.queue.pop(0)
            if deliver(destination, message):
                destination._handle_peer_message(json.loads(message), reply)


class Link:
    initiated_locally = True
    connected = True

    def __init__(self, network: Network, destination: Node, source: Node):
        self.network = network
        self.destination = destination
        self.source = source

    def send(self, message: dict) -> None:
        reply = self.destination.peer_connections[self.source.node_id]
        self.network.queue.append((self.destination, json.dumps(message), reply))

    def enqueue(self, message):

        self.send(message)

        return 0


    def charge(self, tokens):

        pass

    def close(self) -> None:
        pass


@pytest.fixture
def network(four):
    return Network([four.node(index) for index in range(4)])


def test_event_submitted_to_one_node_runs_on_all_four(network):
    network.nodes[0].submit(signed(A))
    network.run()

    for node in network.nodes:
        assert node.local_events == [A]
        assert node.state.balance("bob") == 8
        assert not node.conflicted


def test_node_that_voted_the_alternative_follows_the_certificate(network):
    # No fork: a sender signs two versions, one node votes the other one first.
    voted_b = network.nodes[3]
    assert voted_b._handle_peer_message(encode_vote_request(signed(B)), FakeConnection()) is None
    assert voted_b._quorum.replica.votes() == [B]

    network.nodes[0].submit(signed(A))
    network.run()

    for node in network.nodes:
        assert node.local_events == [A]
        assert node.state.balance("carol") == 0
    assert voted_b._quorum.replica.votes() == [B]
    assert voted_b.equivocations.proofs[0].verify()


def test_votes_split_between_alternatives_give_no_certificate(network):
    # Two votes each, and the quorum is three. A real outcome and not a failure:
    # nothing runs, and the sender is stuck. No node chose, and liveness is not
    # claimed.
    alternatives = {0: A, 1: B, 2: A, 3: B}
    for index, event in alternatives.items():
        network.nodes[index]._handle_peer_message(
            encode_vote_request(signed(event)), FakeConnection()
        )

    network.nodes[0].submit(signed(A))
    network.nodes[1].submit(signed(B))
    network.run()

    for index, node in enumerate(network.nodes):
        assert node.local_events == []
        assert node.state.root() == GENESIS.root()
        assert node._quorum.replica.votes() == [alternatives[index]]
        assert not node.conflicted


def test_one_vote_each_with_two_free_nodes_can_still_certify(network):
    # Which alternative passes depends on the network: here the order of delivery.
    network.nodes[0]._handle_peer_message(
        encode_vote_request(signed(A)), FakeConnection()
    )
    network.nodes[1]._handle_peer_message(
        encode_vote_request(signed(B)), FakeConnection()
    )

    network.nodes[0].submit(signed(A))
    network.nodes[1].submit(signed(B))
    network.run()

    executed = {tuple(node.local_events) for node in network.nodes}
    assert executed == {(A,)}
    for node in network.nodes:
        assert not node.conflicted


def test_lost_certificate_leaves_that_node_behind_without_a_fork(network):
    # Totality is not claimed: the certificate reached only some nodes.
    behind = network.nodes[3]

    def deliver(destination, message):
        # The precommits would let it decide too: they are lost with the certificates.
        return not (destination is behind and ('"CERTIFICATE"' in message or '"ROUND_VOTE"' in message))

    network.nodes[0].submit(signed(A))
    network.run(deliver)

    assert behind.local_events == []
    for node in network.nodes[:3]:
        assert node.local_events == [A]

