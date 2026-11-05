"""Several messages, one transaction (network/quorum.py and PeerConnection.receive_loop).

The rule: a group decides what the same messages decide one by one, and no signature leaves
before the commit. A property test compares the two on random mixes, including conflicts,
repeats and malformed messages. EMPIRICAL.
"""

import json
import random
import socket
import sqlite3
import threading
import time

import pytest

from core.attestation import Committee, QuorumCertificate, Vote
from core.event import Transfer
from core.signed_event import SignedTransfer
from core.state import State
from crypto.identity import Identity
from network.message import (
    decode_vote,
    encode_certificate,
    encode_vote_request,
)
from network.node import Node
from network.node_tls_identity import get_node_tls_config
from network.peer_connection import PeerConnection
from network.quorum import QuorumConfig, QuorumRuntime, VoteStoreError
from network.secure_transport import DuplexTLSStream, SecureTransport

SENDER = Identity.create()
ALICE = SENDER.identity_id
GENESIS = State({ALICE: 1000})
MEMBERS = sorted((Identity.create() for _ in range(4)), key=lambda m: m.public_key)
COMMITTEE = Committee.create([m.public_key for m in MEMBERS], 1, GENESIS)


def spend(nonce: int, receiver: str = "bob") -> SignedTransfer:
    return SignedTransfer.create(SENDER, Transfer(ALICE, receiver, 1, nonce))


def certificate(event: Transfer, signers=(0, 1, 2)) -> QuorumCertificate:
    return QuorumCertificate(
        event,
        tuple(Vote.create(COMMITTEE, MEMBERS[i], event) for i in signers),
    )


def runtime(path) -> QuorumRuntime:
    return QuorumRuntime(QuorumConfig(COMMITTEE, MEMBERS[0], path, create=True), GENESIS)


def random_messages(rng: random.Random, count: int) -> list[dict]:
    messages = []
    for _ in range(count):
        nonce = rng.randrange(6)
        receiver = rng.choice(["bob", "carol"])
        kind = rng.random()
        if kind < 0.5:
            messages.append(encode_vote_request(spend(nonce, receiver)))
        elif kind < 0.9:
            # Only ever one receiver per nonce here, so these conflict with votes and not
            # with each other: a halt has its own test.
            messages.append(encode_certificate(certificate(spend(nonce).transfer)))
        else:
            bad = encode_certificate(certificate(spend(nonce).transfer))
            bad["votes"][0]["signature"] = "00" * 64
            messages.append(bad)
    return messages


def summary(replica) -> tuple:
    return (
        sorted(event.canonical() for event in replica.votes()),
        [event.canonical() for event in replica.executed],
        replica.state.root(),
    )


@pytest.mark.parametrize("seed", range(40))
def test_a_group_decides_what_the_same_messages_decide_one_by_one(tmp_path, seed):
    messages = random_messages(random.Random(seed), 40)
    alone = runtime(tmp_path / "alone.sqlite")
    grouped = runtime(tmp_path / "grouped.sqlite")

    replies_alone = []
    broadcasts_alone = []
    for message in messages:
        output = alone.driver.handle_message(json.loads(json.dumps(message)))
        replies_alone.extend(output.replies)
        broadcasts_alone.extend(output.broadcasts)

    output, error = grouped.handle_group(json.loads(json.dumps(messages)))

    assert error is None
    assert summary(grouped.replica) == summary(alone.replica)
    assert list(output.replies) == replies_alone
    assert list(output.broadcasts) == broadcasts_alone
    grouped.close()
    alone.close()


def test_a_group_survives_a_restart(tmp_path):
    path = tmp_path / "votes.sqlite"
    first = runtime(path)
    messages = [encode_vote_request(spend(0)), encode_certificate(certificate(spend(0).transfer))]
    first.handle_group(messages)
    expected = summary(first.replica)
    first.close()

    again = QuorumRuntime(QuorumConfig(COMMITTEE, MEMBERS[0], path), GENESIS)
    assert summary(again.replica) == expected
    again.close()


def test_a_group_takes_one_transaction(tmp_path):
    path = tmp_path / "votes.sqlite"
    run = runtime(path)
    commits = []
    run._store._connection.set_trace_callback(
        lambda statement: commits.append(statement) if statement == "COMMIT" else None
    )
    run.handle_group([encode_vote_request(spend(n)) for n in range(5)])
    run._store._connection.set_trace_callback(None)
    assert commits == ["COMMIT"]
    run.close()


def test_conflict_inside_a_group_is_refused_as_it_would_be_alone(tmp_path):
    run = runtime(tmp_path / "votes.sqlite")
    output, _ = run.handle_group(
        [encode_vote_request(spend(0, "bob")), encode_vote_request(spend(0, "carol"))]
    )
    assert len(output.replies) == 1
    assert decode_vote(output.replies[0])[0] == spend(0, "bob").transfer
    run.close()


def test_a_halt_inside_a_group_stops_what_comes_after(tmp_path):
    run = runtime(tmp_path / "votes.sqlite")
    a = spend(0, "bob").transfer
    b = spend(0, "carol").transfer
    later = spend(1).transfer
    run.handle_group(
        [
            encode_certificate(certificate(a)),
            encode_certificate(certificate(b)),
            encode_certificate(certificate(later)),
            encode_vote_request(spend(2)),
        ]
    )
    assert run.driver.halted
    assert run.replica.executed == [a]
    assert run.replica.votes() == []
    run.close()


def test_malformed_message_keeps_what_came_before_and_reports_the_error(tmp_path):
    run = runtime(tmp_path / "votes.sqlite")
    output, error = run.handle_group(
        [encode_vote_request(spend(0)), {"type": "VOTE_REQUEST"}, encode_vote_request(spend(1))]
    )
    assert isinstance(error, ValueError)
    assert len(output.replies) == 1
    assert [event.nonce for event in run.replica.votes()] == [0]
    run.close()


def test_failed_commit_sends_nothing_and_leaves_nothing_in_memory(tmp_path):
    path = tmp_path / "votes.sqlite"
    run = runtime(path)
    run.handle_group([encode_vote_request(spend(0)), encode_certificate(certificate(spend(0).transfer))])
    before = summary(run.replica)
    connection = run._store._connection
    real_execute = connection.execute

    class Failing:
        """A connection whose COMMIT fails, with everything else unchanged."""

        def __getattr__(self, name):
            return getattr(connection, name)

        def execute(self, statement, *args):
            if statement == "COMMIT":
                raise sqlite3.OperationalError("disk I/O error")
            return real_execute(statement, *args)

    run._store._connection = Failing()

    with pytest.raises(VoteStoreError):
        run.handle_group(
            [encode_vote_request(spend(1)), encode_certificate(certificate(spend(1).transfer))]
        )

    run._store._connection = connection
    assert summary(run.replica) == before
    # And it goes on: nothing is stuck, and the same messages work now.
    output, _ = run.handle_group(
        [encode_vote_request(spend(1)), encode_certificate(certificate(spend(1).transfer))]
    )
    assert output.replies
    assert len(run.replica.executed) == 2
    run.close()


def test_nothing_is_visible_on_disk_until_the_end_of_a_group(tmp_path):
    path = tmp_path / "votes.sqlite"
    run = runtime(path)
    seen = []

    with run.replica.group():
        assert run.replica.handle_vote_request(spend(0).transfer, spend(0)) is not None
        other = sqlite3.connect(path, timeout=0.05)
        seen.append(other.execute("SELECT count(*) FROM votes").fetchone()[0])
        other.close()

    other = sqlite3.connect(path)
    seen.append(other.execute("SELECT count(*) FROM votes").fetchone()[0])
    other.close()
    assert seen == [0, 1]
    run.close()


# --- Frames that are already here -------------------------------------------------------


def tls_pair():
    listener = socket.create_server(("127.0.0.1", 0))
    accepted = {}

    def accept():
        raw, _ = listener.accept()
        accepted["socket"] = SecureTransport.wrap_server(
            raw,
            SecureTransport.create_server_context(get_node_tls_config("group-b")),
        )

    thread = threading.Thread(target=accept)
    thread.start()
    client = SecureTransport.wrap_client(
        socket.create_connection(listener.getsockname(), timeout=5),
        SecureTransport.create_client_context(get_node_tls_config("group-a")),
        "group-b",
    )
    thread.join()
    listener.close()
    return DuplexTLSStream(client), DuplexTLSStream(accepted["socket"])


@pytest.fixture
def pair():
    left, right = tls_pair()
    yield left, right
    left.close()
    right.close()


def frame(message: dict) -> bytes:
    payload = json.dumps(message).encode()
    return len(payload).to_bytes(4, "big") + payload


def wait_for_frame(stream) -> bool:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if stream.frame_available():
            return True
        time.sleep(0.005)
    return False


def test_frame_available_only_when_the_whole_frame_is_here(pair):
    left, right = pair
    data = frame({"type": "X", "data": "y" * 1000})
    assert not right.frame_available()
    left.sendall(data[:100])
    time.sleep(0.05)
    assert not right.frame_available()
    left.sendall(data[100:])
    assert wait_for_frame(right)
    assert SecureTransport.receive(right) == {"type": "X", "data": "y" * 1000}
    assert not right.frame_available()


def test_bytes_read_ahead_are_not_lost(pair):
    left, right = pair
    left.sendall(frame({"n": 1}) + frame({"n": 2}) + frame({"n": 3})[:5])
    assert wait_for_frame(right)
    assert SecureTransport.receive(right) == {"n": 1}
    assert right.frame_available()
    assert SecureTransport.receive(right) == {"n": 2}
    assert not right.frame_available()
    left.sendall(frame({"n": 3})[5:])
    assert SecureTransport.receive(right) == {"n": 3}


def test_a_bad_length_counts_as_available_and_reading_it_raises(pair):
    left, right = pair
    left.sendall((2**31).to_bytes(4, "big"))
    assert wait_for_frame(right)
    with pytest.raises(ValueError):
        SecureTransport.receive(right)


def _peer_on(stream) -> PeerConnection:
    connection = PeerConnection("x", "127.0.0.1", 1)
    connection.connection = stream
    return connection


def test_a_frame_that_stops_halfway_does_not_hold_back_those_before_it(pair):
    left, right = pair
    received = []
    done = threading.Event()

    def batch(messages, _connection):
        received.append(list(messages))
        done.set()

    connection = _peer_on(right)
    threading.Thread(
        target=connection.receive_loop,
        args=(lambda *_: None, batch),
        daemon=True,
    ).start()
    left.sendall(frame({"n": 1}) + frame({"n": 2})[:3])
    assert done.wait(3)
    assert received == [[{"n": 1}]]
    connection.close()


def test_frames_that_arrived_together_are_handled_together(pair):
    left, right = pair
    left.sendall(b"".join(frame({"n": n}) for n in range(5)))
    time.sleep(0.1)
    received = []
    done = threading.Event()

    def batch(messages, _connection):
        received.extend(messages)
        if len(received) == 5:
            done.set()

    connection = _peer_on(right)
    calls = []
    original = batch

    def counted(messages, c):
        calls.append(len(messages))
        original(messages, c)

    threading.Thread(
        target=connection.receive_loop,
        args=(lambda *_: None, counted),
        daemon=True,
    ).start()
    assert done.wait(3)
    assert received == [{"n": n} for n in range(5)]
    assert calls == [5]
    connection.close()


def test_a_batch_has_a_limit(pair, monkeypatch):
    monkeypatch.setattr(PeerConnection, "MAX_RECEIVED_TOGETHER", 2)
    left, right = pair
    left.sendall(b"".join(frame({"n": n}) for n in range(5)))
    time.sleep(0.1)
    calls = []
    done = threading.Event()

    def batch(messages, _connection):
        calls.append(len(messages))
        if sum(calls) == 5:
            done.set()

    connection = _peer_on(right)
    threading.Thread(
        target=connection.receive_loop,
        args=(lambda *_: None, batch),
        daemon=True,
    ).start()
    assert done.wait(3)
    assert max(calls) <= 2
    connection.close()


def test_malformed_frame_after_good_ones_closes_after_handling_them(pair):
    left, right = pair
    left.sendall(frame({"n": 1}) + (5).to_bytes(4, "big") + b"nope!")
    time.sleep(0.1)
    received = []
    connection = _peer_on(right)
    closed = threading.Event()
    connection.on_disconnect = lambda _c: closed.set()
    thread = threading.Thread(
        target=connection.receive_loop,
        args=(lambda *_: None, lambda messages, _c: received.extend(messages)),
        daemon=True,
    )
    thread.start()
    assert closed.wait(3)
    assert received == [{"n": 1}]
    assert connection.connection is None


# --- Through a Node ---------------------------------------------------------------------


def test_node_group_with_other_messages_between_keeps_the_order(tmp_path):
    node = Node(
        "group-node",
        GENESIS,
        quorum=QuorumConfig(COMMITTEE, MEMBERS[0], tmp_path / "v.sqlite", create=True),
    )
    order = []
    real = node._handle_quorum_group

    def spy(messages, connection):
        if messages:
            order.append([m["type"] for m in messages])
        real(messages, connection)

    node._handle_quorum_group = spy
    sent = []

    class Connection:
        initiated_locally = True

        def send(self, message):
            sent.append(message["type"])

        enqueue = send

    node._handle_peer_messages(
        [
            encode_vote_request(spend(0)),
            encode_vote_request(spend(1)),
            {"type": "EVENT_SYNC"},
            encode_vote_request(spend(2)),
        ],
        Connection(),
    )
    assert order == [["VOTE_REQUEST", "VOTE_REQUEST"], ["VOTE_REQUEST"]]
    assert sent == ["VOTE", "VOTE", "VOTE"]
    node.stop()


def test_node_group_with_a_malformed_message_raises_after_sending(tmp_path):
    node = Node(
        "group-node-2",
        GENESIS,
        quorum=QuorumConfig(COMMITTEE, MEMBERS[0], tmp_path / "v.sqlite", create=True),
    )
    sent = []

    class Connection:
        initiated_locally = True

        def send(self, message):
            sent.append(message["type"])

        enqueue = send

    with pytest.raises(ValueError):
        node._handle_peer_messages(
            [encode_vote_request(spend(0)), {"type": "VOTE_REQUEST"}],
            Connection(),
        )

    assert sent == ["VOTE"]
    node.stop()


def test_no_signature_before_the_commit_of_a_group(tmp_path):
    # The output of a group comes back only after `with group()` has ended. A signature
    # computed inside goes nowhere if the commit fails: test_failed_commit... shows that.
    run = runtime(tmp_path / "votes.sqlite")
    order = []
    real_group = run.replica.group

    class Spy:
        def __enter__(self):
            self.inner = real_group()
            return self.inner.__enter__()

        def __exit__(self, *args):
            result = self.inner.__exit__(*args)
            order.append("commit")
            return result

    run.replica.group = Spy
    output, _ = run.handle_group([encode_vote_request(spend(0)), encode_vote_request(spend(1))])
    order.append(("output", len(output.replies)))
    assert order == ["commit", ("output", 2)]
    run.close()


def test_failed_commit_of_a_closure_leaves_the_epoch_as_it_was(tmp_path):
    from core.attestation import EpochChange, EpochClosure, EpochReport, Governance
    from network.message import encode_epoch_closure

    signers = [Identity.create() for _ in range(2)]
    governance = Governance(tuple(sorted(s.public_key for s in signers)), 2)
    run = QuorumRuntime(
        QuorumConfig(COMMITTEE, MEMBERS[0], tmp_path / "v.sqlite", create=True, governance=governance),
        GENESIS,
    )
    change = EpochChange.create(COMMITTEE, COMMITTEE.members, 1, governance, signers)
    reports = tuple(
        EpochReport.create(COMMITTEE, MEMBERS[i], change.change_id, ()) for i in range(3)
    )
    candidate = EpochClosure(change, reports)
    event = candidate.event(governance, COMMITTEE)
    closure = EpochClosure(
        change,
        reports,
        tuple(Vote.create(COMMITTEE, MEMBERS[i], event) for i in range(3)),
    )
    connection = run._store._connection
    real_execute = connection.execute

    class Failing:
        def __getattr__(self, name):
            return getattr(connection, name)

        def execute(self, statement, *args):
            if statement == "COMMIT":
                raise sqlite3.OperationalError("disk I/O error")
            return real_execute(statement, *args)

    run._store._connection = Failing()
    message = encode_epoch_closure(closure)

    with pytest.raises(VoteStoreError):
        run.handle_group([message, encode_vote_request(spend(0))])

    run._store._connection = connection
    assert run.replica.committee.epoch == 0

    # The same closure installs now.
    run.handle_group([message])
    assert run.replica.committee.epoch == 1
    run.close()


def test_a_message_too_large_for_a_frame_stops_nothing(tmp_path, caplog):
    # A closure over too many events does not fit. It must be logged, not kill the reader.
    from network.quorum import DriverOutput

    node = Node(
        "large-node",
        GENESIS,
        quorum=QuorumConfig(COMMITTEE, MEMBERS[0], tmp_path / "v.sqlite", create=True),
    )

    class TooLarge:
        initiated_locally = True
        closed = False

        def send(self, _message):
            raise ValueError("MESSAGE TOO LARGE")

        enqueue = send

        def close(self):
            self.closed = True

    peer = TooLarge()
    node.peer_connections["p"] = peer
    node._send_quorum_output(DriverOutput(({"type": "X"},), ({"type": "EPOCH_CLOSURE"},)), peer)

    assert not peer.closed
    assert "p" in node.peer_connections
    assert sum("too large" in record.message for record in caplog.records) == 2
    node.peer_connections.clear()
    node.stop()
