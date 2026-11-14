"""Differential C: four nodes on real TLS, one of them faulty.

Three honest `Node`s and a member of the committee that does what the protocol forbids. The
"differential" is between what the honest nodes end up with and what the theorems of the
model promise, checked as properties of each run:

- `no_double_spend`: no two honest logs hold different events for one `(sender, nonce)`;
- `state_is_derive`: the state of each node is what StateDeriver gives for its log;
- `convergence_after_exchange`: once synchronized, the honest nodes hold the same state.

EMPIRICAL, for `n = 4`, `f = 1`, on these scenarios: nothing here is compared with Lean, and
none of it is a proof about the code. Convergence is reached here because the network
delivers. It is not a liveness result.

A real SIGKILL over TLS is not here: the certificates of the test exist only in its process.
`tests/test_quorum_byzantine.py` kills the process for votes and for the halt, and here a
node restarts from its file after `stop`.
"""

import itertools
import random
import socket
import threading
import types
import time

import pytest

from core.attestation import PRECOMMIT, Committee, QuorumCertificate, Vote
from core.derive import StateDeriver
from core.event import Transfer
from core.signed_event import SignedTransfer
from core.state import State
from crypto.identity import Identity
from network.handshake import Handshake
from network.message import (
    decode_vote,
    encode_certificate,
    encode_certificate_sync,
    encode_certificate_sync_request,
    encode_round_vote,
    encode_vote_request,
)
from network.node import Node
from network.node_tls_identity import get_node_tls_config
from network.peer import Peer
from network.peer_connection import PeerConnection
from network.quorum import QuorumConfig
from network.secure_transport import DuplexTLSStream, SecureTransport

SENDERS = [Identity.create() for _ in range(3)]
GENESIS = State({sender.identity_id: 1000 for sender in SENDERS})
MEMBERS = sorted((Identity.create() for _ in range(4)), key=lambda m: m.public_key)
COMMITTEE = Committee.create([m.public_key for m in MEMBERS], 1, GENESIS)
FAULTY = 3
SENDER = SENDERS[0]


def transfer(sender: Identity, nonce: int, receiver: str = "bob", parents=()) -> SignedTransfer:
    return SignedTransfer.create(
        sender,
        Transfer(sender.identity_id, receiver, 1, nonce, tuple(parents)),
    )


def wait_until(condition, seconds: float = 20.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return condition()


class FaultyMember:
    """Member 3 of the committee, with its key and with no rule."""

    def __init__(self, nodes, *, receive_buffer: int | None = None, read: bool = True):
        self.identity = MEMBERS[FAULTY]
        self.connections = {}
        self.votes: dict[bytes, tuple[Transfer, dict[int, Vote]]] = {}
        self._lock = threading.Lock()
        self._read = read
        self._receive_buffer = receive_buffer

        for node in nodes:
            self.connections[node.node_id] = self._connect(node)

    def _connect(self, node) -> PeerConnection:
        tag = f"faulty-{node.node_id}"
        config = get_node_tls_config(tag)
        host, port = node.address()
        raw = socket.socket()

        if self._receive_buffer is not None:
            raw.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, self._receive_buffer)

        raw.settimeout(5)
        raw.connect((host, port))
        connection = PeerConnection(tag, "127.0.0.1", 1)
        wrapped = SecureTransport.wrap_client(
            raw,
            SecureTransport.create_client_context(config),
            node.node_id,
        )
        SecureTransport.send(wrapped, Handshake(tag, "127.0.0.1", 1).encode())
        SecureTransport.receive(wrapped)
        wrapped.settimeout(None)
        connection.connection = DuplexTLSStream(wrapped)
        connection.on_disconnect = None

        if self._read:
            threading.Thread(
                target=connection.receive_loop,
                args=(self._on_message,),
                daemon=True,
            ).start()

        return connection

    def _on_message(self, message, _connection) -> None:
        if message.get("type") != "VOTE":
            return

        event, vote = decode_vote(message)

        with self._lock:
            _, votes = self.votes.setdefault(event.canonical(), (event, {}))
            votes[vote.validator] = vote

    def own_vote(self, event: Transfer) -> Vote:
        return Vote.create(COMMITTEE, self.identity, event)

    def ask_vote(self, node, signed: SignedTransfer) -> None:
        self.connections[node.node_id].send(encode_vote_request(signed))

    def collected(self, event: Transfer) -> dict[int, Vote]:
        with self._lock:
            return dict(self.votes.get(event.canonical(), (event, {}))[1])

    def certificate(self, event: Transfer) -> QuorumCertificate:
        votes = self.collected(event)
        votes[FAULTY] = self.own_vote(event)
        return QuorumCertificate(event, tuple(votes[v] for v in sorted(votes)))

    def prepare_and_precommit(self, node, signed: SignedTransfer) -> None:
        """
        Three votes of round 0 are a prepare certificate, not a decision. This member sends it to
        `node` and its own precommit to all: with those of the two honest nodes, a decision.
        """
        precommit = Vote.create_phase(COMMITTEE, self.identity, signed.transfer, PRECOMMIT, 0)
        message = encode_round_vote(signed.transfer, precommit, PRECOMMIT, 0)
        message["public_key"] = signed.public_key.hex()
        message["sender_signature"] = signed.signature.hex()
        for connection in self.connections.values():
            connection.send(message)
        self.connections[node.node_id].send(encode_certificate(self.certificate(signed.transfer)))

    def close(self) -> None:
        for connection in self.connections.values():
            connection.close()


@pytest.fixture
def make_nodes(tmp_path):
    made = []

    def make(sync_interval: float | None = 0.2, indexes=(0, 1, 2), suffix: str = ""):
        tag = tmp_path.name[-10:].replace("_", "-")
        nodes = [
            Node(
                f"n{index}-{tag}{suffix}",
                GENESIS,
                quorum=QuorumConfig(
                    COMMITTEE,
                    MEMBERS[index],
                    tmp_path / f"{index}.sqlite",
                    create=True,
                    sync_interval=sync_interval,
                ),
            )
            for index in indexes
        ]
        made.extend(nodes)

        for node in nodes:
            node.start()

        return nodes

    yield make

    for node in made:
        node.stop()


def link(nodes) -> None:
    for low, high in itertools.combinations(nodes, 2):
        host, port = high.address()
        assert low.connect_peer(Peer(node_id=high.node_id, host=host, port=port))

    assert wait_until(lambda: all(len(n.peer_connections) >= len(nodes) - 1 for n in nodes))


def assert_no_double_spend(nodes) -> None:
    seen = {}
    for node in nodes:
        for event in node.local_events:
            first = seen.setdefault((event.sender, event.nonce), event)
            assert first.canonical() == event.canonical()


def assert_state_is_derive(nodes) -> None:
    for node in nodes:
        # Under the lock, as the API reads them: the node publishes its events and then its state, so
        # a reader without it can see one before the other. The CI saw that once, on a loaded machine.
        with node._state_lock:
            events = list(node.local_events)
            root = node.state.root()

        assert root == StateDeriver.apply_events(GENESIS.copy(), events).root()


def same_state(nodes) -> bool:
    return len({node.state.root() for node in nodes}) == 1


def assert_the_theorems_hold(nodes) -> None:
    assert_no_double_spend(nodes)
    assert_state_is_derive(nodes)
    assert same_state(nodes)
    for node in nodes:
        assert not node.conflicted


# --- Scenarios --------------------------------------------------------------------------


@pytest.mark.filterwarnings("error::pytest.PytestUnhandledThreadExceptionWarning")
def test_equivocation_with_a_faulty_voter_gives_one_event_everywhere(make_nodes):
    nodes = make_nodes()
    link(nodes)
    faulty = FaultyMember(nodes)
    first = transfer(SENDER, 0, "alternative-a")
    second = transfer(SENDER, 0, "alternative-b")

    # Each honest member sees one alternative first: two for b, one for a.
    faulty.ask_vote(nodes[0], first)
    faulty.ask_vote(nodes[1], second)
    faulty.ask_vote(nodes[2], second)
    assert wait_until(lambda: len(faulty.collected(second.transfer)) == 2)
    assert wait_until(lambda: len(faulty.collected(first.transfer)) == 1)

    # Asking again changes nothing: the first vote is a lock.
    faulty.ask_vote(nodes[0], second)
    faulty.ask_vote(nodes[1], first)
    time.sleep(0.2)
    assert len(faulty.collected(second.transfer)) == 2

    # With its own vote the faulty member has a certificate for b, and none for a. It gives
    # it to one node only, and the others have to find it.
    assert len(faulty.certificate(first.transfer).votes) == 2
    faulty.connections[nodes[0].node_id].send(
        encode_certificate(faulty.certificate(second.transfer))
    )

    assert wait_until(lambda: all(n.local_events == [second.transfer] for n in nodes))
    assert_the_theorems_hold(nodes)
    faulty.close()


@pytest.mark.filterwarnings("error::pytest.PytestUnhandledThreadExceptionWarning")
def test_forged_certificates_change_nothing_and_halt_nothing(make_nodes):
    nodes = make_nodes()
    link(nodes)
    faulty = FaultyMember(nodes)
    honest = transfer(SENDER, 0, "honest")
    assert nodes[0].submit(honest)
    assert wait_until(lambda: all(n.local_events == [honest.transfer] for n in nodes))

    fake_event = transfer(SENDER, 0, "fake").transfer
    signature = faulty.own_vote(fake_event).signature
    forged = QuorumCertificate(
        fake_event,
        tuple(Vote(index, signature) for index in (0, 1, FAULTY)),
    )

    for node in nodes:
        connection = faulty.connections[node.node_id]
        connection.send(encode_certificate(forged))
        connection.send(encode_certificate_sync([forged]))

    time.sleep(0.5)
    assert all(n.local_events == [honest.transfer] for n in nodes)
    assert not any(n._quorum.driver.halted for n in nodes)
    assert_the_theorems_hold(nodes)
    faulty.close()


@pytest.mark.filterwarnings("error::pytest.PytestUnhandledThreadExceptionWarning")
@pytest.mark.parametrize(
    "frame",
    [
        (5).to_bytes(4, "big") + b"nope!",
        (0).to_bytes(4, "big"),
        (2**31).to_bytes(4, "big"),
        (200_000).to_bytes(4, "big") + b"[" * 200_000,
    ],
    ids=["not json", "empty", "too long", "nested"],
)
def test_malformed_frames_cost_only_the_faulty_connection(make_nodes, frame):
    nodes = make_nodes()
    link(nodes)
    faulty = FaultyMember(nodes)

    for node in nodes:
        faulty.connections[node.node_id].connection.sendall(frame)

    assert wait_until(lambda: all(len(n.peer_connections) == 2 for n in nodes))
    event = transfer(SENDER, 0)
    assert nodes[0].submit(event)
    assert wait_until(lambda: all(n.local_events == [event.transfer] for n in nodes))
    assert_the_theorems_hold(nodes)
    faulty.close()


@pytest.mark.filterwarnings("error::pytest.PytestUnhandledThreadExceptionWarning")
def test_malformed_messages_of_each_type_cost_only_the_faulty_connection(make_nodes):
    nodes = make_nodes()
    link(nodes)

    for message in (
        {"type": "VOTE_REQUEST"},
        {"type": "VOTE", "transfer": 1},
        {"type": "CERTIFICATE", "transfer": {}, "votes": []},
        {"type": "CERTIFICATE_SYNC", "certificates": 1},
        {"type": "CERTIFICATE_SYNC_REQUEST", "frontier": [["x", -1]]},
    ):
        faulty = FaultyMember(nodes)
        for node in nodes:
            faulty.connections[node.node_id].send(message)
        assert wait_until(lambda: all(len(n.peer_connections) == 2 for n in nodes))
        faulty.close()

    event = transfer(SENDER, 0)
    assert nodes[1].submit(event)
    assert wait_until(lambda: all(n.local_events == [event.transfer] for n in nodes))
    assert_the_theorems_hold(nodes)


@pytest.mark.filterwarnings("error::pytest.PytestUnhandledThreadExceptionWarning")
def test_a_peer_that_does_not_read_does_not_hold_the_others(make_nodes, monkeypatch):
    monkeypatch.setattr(DuplexTLSStream, "SEND_TIMEOUT", 1.0)
    nodes = make_nodes(sync_interval=None)
    link(nodes)
    victim = nodes[0]

    # A log long enough for its answers to fill the buffers of the connection quickly.
    events = [transfer(SENDER, nonce) for nonce in range(25)]
    for event in events:
        assert victim.submit(event)
    assert wait_until(
        lambda: all(len(n.local_events) == len(events) for n in nodes),
        seconds=30,
    )

    faulty = FaultyMember([victim], receive_buffer=4096, read=False)
    connection = faulty.connections[victim.node_id]
    assert wait_until(lambda: len(victim.peer_connections) == 3)
    request = encode_certificate_sync_request({})

    def flood():
        try:
            while True:
                connection.send(request)
        except OSError:
            pass

    threading.Thread(target=flood, daemon=True).start()

    # The victim's answers stop, its send times out, and the connection goes.
    assert wait_until(lambda: len(victim.peer_connections) == 2, seconds=30)

    late = transfer(SENDER, len(events))
    assert victim.submit(late)
    assert wait_until(
        lambda: all(len(n.local_events) == len(events) + 1 for n in nodes),
        seconds=15,
    )
    assert_the_theorems_hold(nodes)
    faulty.close()


@pytest.mark.filterwarnings("error::pytest.PytestUnhandledThreadExceptionWarning")
def test_a_broadcast_goes_on_after_a_peer_that_blocks_it(make_nodes, monkeypatch):
    # The order of a broadcast is the order of the connections, so the faulty peer comes first.
    # Its queue is full, and the others must not notice. That a slow peer does not delay them
    # is in tests/test_peer_queue_and_fragments.py.
    monkeypatch.setattr(DuplexTLSStream, "SEND_TIMEOUT", 0.5)
    nodes = make_nodes(sync_interval=None)
    link(nodes)
    victim, other, *_ = nodes
    faulty = FaultyMember([victim], receive_buffer=4096, read=False)
    stream = faulty.connections[victim.node_id]
    assert wait_until(lambda: len(victim.peer_connections) == 3)
    blocked = victim.peer_connections[f"faulty-{victim.node_id}"]
    def queue_is_full(message):
        raise ConnectionError("PEER IS TOO FAR BEHIND")

    blocked.enqueue = queue_is_full
    with victim._peer_connections_lock:
        victim.peer_connections = {
            f"faulty-{victim.node_id}": blocked,
            **{k: v for k, v in victim.peer_connections.items() if v is not blocked},
        }

    event = transfer(SENDER, 0)
    assert victim.submit(event)
    assert wait_until(lambda: all(n.local_events == [event.transfer] for n in nodes))
    assert f"faulty-{victim.node_id}" not in victim.peer_connections
    stream.close()
    assert_the_theorems_hold([victim, other])


def test_a_reader_without_the_lock_can_see_the_events_before_the_state(make_nodes, monkeypatch):
    # Why the helper above takes the lock, shown with no timing: what a reader sees while the node
    # is publishing, in the middle of it.
    [node] = make_nodes(sync_interval=None, indexes=(0,))
    event = transfer(SENDER, 0)
    assert node.submit(event)
    seen = []
    real = State.copy

    def spy(state):
        seen.append((len(node.local_events), node.state.nonce(event.transfer.sender)))
        return real(state)

    monkeypatch.setattr(State, "copy", spy)
    # All four: the votes of round 0 that decide.
    votes = tuple(Vote.create(COMMITTEE, member, event.transfer) for member in MEMBERS)
    node._handle_quorum_message(encode_certificate(QuorumCertificate(event.transfer, votes)), None)
    assert (1, 0) in seen


def test_a_queue_that_is_full_does_not_stop_a_broadcast_to_the_others():
    # With no network. In the test above the faulty peer can drop out before the broadcast on a
    # loaded machine, and then that test proves nothing about this rule.
    sent = []
    dropped = []

    class Target:
        def __init__(self, name, full=False):
            self.name = name
            self.full = full

        def enqueue(self, message):
            if self.full:
                raise ConnectionError("PEER IS TOO FAR BEHIND")
            sent.append((self.name, message))

    node = types.SimpleNamespace(
        _peer_connections_lock=threading.Lock(),
        peer_connections={
            "full": Target("full", full=True),
            "first": Target("first"),
            "second": Target("second"),
        },
        _disconnect_peer_connection=lambda node_id, target: dropped.append(node_id),
    )
    output = types.SimpleNamespace(replies=(), broadcasts=({"type": "A"}, {"type": "B"}))

    Node._send_quorum_output(node, output, None)

    assert sent == [
        ("first", {"type": "A"}),
        ("second", {"type": "A"}),
        ("first", {"type": "B"}),
        ("second", {"type": "B"}),
    ]
    assert dropped == ["full", "full"]


@pytest.mark.filterwarnings("error::pytest.PytestUnhandledThreadExceptionWarning")
def test_a_node_that_was_away_catches_up_when_it_connects(make_nodes):
    nodes = make_nodes()
    link(nodes[:2])
    late = nodes[2]
    faulty = FaultyMember(nodes)
    events = []

    # Two honest members and the faulty one form the quorum, without the node that is away.
    for nonce in range(5):
        event = transfer(SENDER, nonce)
        faulty.ask_vote(nodes[0], event)
        faulty.ask_vote(nodes[1], event)
        assert wait_until(lambda: len(faulty.collected(event.transfer)) == 2)
        faulty.prepare_and_precommit(nodes[0], event)
        events.append(event.transfer)

    assert wait_until(lambda: all(n.local_events == events for n in nodes[:2]))
    assert late.local_events == []
    faulty.close()

    host, port = nodes[1].address()
    assert late.connect_peer(Peer(node_id=nodes[1].node_id, host=host, port=port))

    assert wait_until(lambda: late.local_events == events)
    assert_the_theorems_hold(nodes)


def _node_ahead_and_one_behind(make_nodes):
    ahead, other, behind = make_nodes(sync_interval=None)
    link([ahead, other])
    faulty = FaultyMember([ahead, other])
    event = transfer(SENDER, 0)
    faulty.ask_vote(ahead, event)
    faulty.ask_vote(other, event)
    assert wait_until(lambda: len(faulty.collected(event.transfer)) == 2)
    faulty.prepare_and_precommit(ahead, event)
    assert wait_until(lambda: ahead.local_events == [event.transfer])
    faulty.close()
    return ahead, behind, event.transfer


@pytest.mark.filterwarnings("error::pytest.PytestUnhandledThreadExceptionWarning")
def test_with_no_intervals_the_node_that_connects_asks_at_once(make_nodes):
    ahead, behind, event = _node_ahead_and_one_behind(make_nodes)
    host, port = ahead.address()
    assert behind.connect_peer(Peer(node_id=ahead.node_id, host=host, port=port))
    assert wait_until(lambda: behind.local_events == [event], seconds=5)


def test_connecting_asks_before_connect_peer_returns(make_nodes, monkeypatch):
    # On a real network the peer usually connects back and that connection asks too, which
    # hides a missing request on this side. So this looks at the call itself.
    ahead, behind, _ = _node_ahead_and_one_behind(make_nodes)
    asked = []
    real = Node._request_certificates

    def spy(self, connection):
        asked.append((self.node_id, connection.initiated_locally))
        real(self, connection)

    monkeypatch.setattr(Node, "_request_certificates", spy)
    host, port = ahead.address()
    assert behind.connect_peer(Peer(node_id=ahead.node_id, host=host, port=port))
    assert (behind.node_id, True) in asked


@pytest.mark.filterwarnings("error::pytest.PytestUnhandledThreadExceptionWarning")
def test_with_no_intervals_the_node_connected_to_asks_at_once(make_nodes):
    ahead, behind, event = _node_ahead_and_one_behind(make_nodes)
    host, port = behind.address()
    assert ahead.connect_peer(Peer(node_id=behind.node_id, host=host, port=port))
    assert wait_until(lambda: behind.local_events == [event], seconds=5)


@pytest.mark.filterwarnings("error::pytest.PytestUnhandledThreadExceptionWarning")
def test_a_node_asks_again_at_intervals(make_nodes, monkeypatch):
    # The interval is the policy of asking what one lacks: a node that is linked and running asks
    # again at intervals, not only when a connection is new, and not only while it waits for
    # something. Nothing else happens in the loop, so the asks are only the ones of the clock.
    nodes = make_nodes()
    link(nodes)
    assert wait_until(lambda: all(len(n.peer_connections) == 2 for n in nodes))

    asked = []
    real = Node._request_certificates

    def spy(self, connection):
        asked.append(self.node_id)
        real(self, connection)

    monkeypatch.setattr(Node, "_request_certificates", spy)
    before = len(asked)
    assert wait_until(lambda: len(asked) > before + 2, seconds=10)


@pytest.mark.filterwarnings("error::pytest.PytestUnhandledThreadExceptionWarning")
def test_a_restarted_node_recovers_what_it_missed(make_nodes, tmp_path):
    nodes = make_nodes()
    link(nodes)
    faulty = FaultyMember(nodes[:2])
    before = transfer(SENDER, 0)
    assert nodes[0].submit(before)
    assert wait_until(lambda: all(n.local_events == [before.transfer] for n in nodes))

    nodes[2].stop()
    missed = []

    for nonce in range(1, 4):
        event = transfer(SENDER, nonce)
        faulty.ask_vote(nodes[0], event)
        faulty.ask_vote(nodes[1], event)
        assert wait_until(lambda: len(faulty.collected(event.transfer)) == 2)
        faulty.prepare_and_precommit(nodes[1], event)
        missed.append(event.transfer)

    assert wait_until(lambda: nodes[1].local_events == [before.transfer, *missed])
    faulty.close()

    back = make_nodes(indexes=(2,), suffix="-back")[0]
    assert back.local_events == [before.transfer]
    host, port = nodes[0].address()
    assert back.connect_peer(Peer(node_id=nodes[0].node_id, host=host, port=port))

    assert wait_until(lambda: back.local_events == [before.transfer, *missed])
    assert_the_theorems_hold([nodes[0], nodes[1], back])


@pytest.mark.filterwarnings("error::pytest.PytestUnhandledThreadExceptionWarning")
@pytest.mark.parametrize("seed", range(3))
def test_random_traffic_with_a_faulty_member(make_nodes, seed):
    # Honest traffic from all three senders, with chains across senders, while the faulty
    # member equivocates on nonces of its own. The honest senders' events can only be
    # certified by the three honest nodes.
    rng = random.Random(seed)
    nodes = make_nodes()
    link(nodes)
    faulty = FaultyMember(nodes)
    next_nonce = {sender.identity_id: 0 for sender in SENDERS[:2]}
    previous = None
    submitted = []
    cheater = SENDERS[2]

    for step in range(40):
        if rng.random() < 0.25:
            alternatives = [transfer(cheater, step, f"cheat-{step}-{i}") for i in range(2)]
            for node in nodes:
                faulty.ask_vote(node, rng.choice(alternatives))
            continue

        sender = rng.choice(SENDERS[:2])
        parents = (previous.event_id(),) if previous is not None and rng.random() < 0.5 else ()
        signed = transfer(sender, next_nonce[sender.identity_id], "bob", parents)
        next_nonce[sender.identity_id] += 1
        assert rng.choice(nodes).submit(signed)
        previous = signed.transfer
        submitted.append(signed.transfer)

    expected = {event.event_id() for event in submitted}

    assert wait_until(
        lambda: all(
            expected <= {event.event_id() for event in node.local_events}
            for node in nodes
        ),
        seconds=40,
    )
    assert wait_until(lambda: same_state(nodes), seconds=10)
    assert_the_theorems_hold(nodes)
    faulty.close()


@pytest.mark.filterwarnings("error::pytest.PytestUnhandledThreadExceptionWarning")
def test_two_certificates_in_conflict_over_real_tls_halt_and_choose_nothing(make_nodes):
    # Beyond the hypothesis: more than f faulty members. A node must stop, not choose.
    nodes = make_nodes()
    link(nodes)
    faulty = FaultyMember(nodes)
    event_a = transfer(SENDER, 0, "a").transfer
    event_b = transfer(SENDER, 0, "b").transfer

    def certificate(event):
        return QuorumCertificate(
            event,
            tuple(Vote.create(COMMITTEE, member, event) for member in MEMBERS),
        )

    connection = faulty.connections[nodes[0].node_id]
    connection.send(encode_certificate(certificate(event_a)))
    assert wait_until(lambda: nodes[0].local_events == [event_a])
    connection.send(encode_certificate_sync([certificate(event_b)]))

    assert wait_until(lambda: nodes[0].conflicted)
    assert nodes[0].local_events == [event_a]
    assert nodes[0].state.balance("b") == 0
    faulty.close()
