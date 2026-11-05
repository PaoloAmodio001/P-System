"""A peer that does not read holds back only itself, and a message can exceed a frame."""

import base64
import hashlib
import json
import socket
import threading
import time

import pytest

from core.attestation import Committee, EpochChange, Governance
from core.event import Transfer
from core.signed_event import SignedTransfer
from core.state import State
from crypto.identity import Identity
from network.fragments import (
    FRAGMENT_DATA_SIZE,
    MAX_ASSEMBLED_SIZE,
    FragmentAssembler,
    split_payload,
)
from network.node import Node
from network.peer import Peer
from network.peer_connection import PeerConnection
from network.quorum import QuorumConfig
from network.secure_transport import MAX_MESSAGE_SIZE, SecureTransport


def assembled(fragments) -> bytes | None:
    assembler = FragmentAssembler()
    result = None
    for fragment in fragments:
        assert result is None
        result = assembler.add(fragment)
    return result


def send_behind(connection, *messages):
    """A socket pair holds little: without this, a large frame waits for a reader forever."""

    def run():
        for message in messages:
            SecureTransport.send(connection, message)

    threading.Thread(target=run, daemon=True).start()


def pair():
    left, right = socket.socketpair()
    connection = PeerConnection("peer", "127.0.0.1", 1)
    connection.connection = left
    connection_right = PeerConnection("peer", "127.0.0.1", 1)
    connection_right.connection = right
    return connection, connection_right


LARGE = "x" * (MAX_MESSAGE_SIZE + 1024)


# Fragments alone.

def test_a_payload_comes_back_whole():
    payload = bytes(range(256)) * (FRAGMENT_DATA_SIZE // 100)
    fragments = split_payload("EPOCH_CLOSURE", payload)
    assert len(fragments) == 3
    assert assembled(fragments) == payload


def test_every_fragment_fits_a_frame():
    fragment = split_payload("EPOCH_CLOSURE", b"x" * FRAGMENT_DATA_SIZE)[0]
    assert len(SecureTransport.encode_payload(fragment)) <= MAX_MESSAGE_SIZE


@pytest.mark.parametrize("carries", ["VOTE", "CERTIFICATE_SYNC", "HANDSHAKE", None])
def test_only_the_messages_of_a_closure_may_be_split(carries):
    with pytest.raises(ValueError):
        split_payload(carries, b"x")


def test_nothing_beyond_the_limit_is_split():
    class Long(bytes):
        def __len__(self):
            return MAX_ASSEMBLED_SIZE + 1

    with pytest.raises(ValueError):
        split_payload("EPOCH_CLOSURE", Long(b"x"))


def test_the_limit_itself_is_allowed():
    fragments = split_payload("EPOCH_CLOSURE", b"x" * MAX_ASSEMBLED_SIZE)
    assert fragments[0]["total"] == MAX_ASSEMBLED_SIZE // FRAGMENT_DATA_SIZE
    assert assembled(fragments[:1]) is None


def good(total=3):
    return split_payload("EPOCH_CLOSURE", b"y" * (FRAGMENT_DATA_SIZE * (total - 1) + 5))


@pytest.mark.parametrize(
    "change",
    [
        {"index": 1},
        {"index": -1},
        {"index": True},
        {"index": "0"},
        {"index": 3},
        {"total": 0},
        {"total": True},
        {"total": "3"},
        {"total": MAX_ASSEMBLED_SIZE // FRAGMENT_DATA_SIZE + 1},
        {"carries": "VOTE"},
        {"carries": ["EPOCH_CLOSURE"]},
        {"id": "z" * 64},
        {"id": "A" * 64},
        {"id": "a" * 63},
        {"id": 7},
        {"data": 7},
        {"data": "not base64!"},
        {"data": ""},
        {"data": base64.b64encode(b"x" * (FRAGMENT_DATA_SIZE + 1)).decode()},
    ],
    ids=str,
)
def test_a_bad_first_fragment_is_refused(change):
    with pytest.raises(ValueError):
        FragmentAssembler().add({**good()[0], **change})


def test_false_is_not_the_first_index():
    with pytest.raises(ValueError):
        FragmentAssembler().add({**good()[0], "index": False})


def test_true_is_not_a_total_of_one():
    fragment = split_payload("EPOCH_CLOSURE", b"x")[0]
    with pytest.raises(ValueError):
        FragmentAssembler().add({**fragment, "total": True})


def test_a_total_of_zero_is_refused_even_with_the_right_digest():
    fragment = split_payload("EPOCH_CLOSURE", b"x")[0]
    with pytest.raises(ValueError):
        FragmentAssembler().add({**fragment, "total": 0})


def test_base64_with_other_characters_is_refused():
    fragment = split_payload("EPOCH_CLOSURE", b"\0\0\0")[0]
    assert fragment["data"] == "AAAA"
    with pytest.raises(ValueError):
        FragmentAssembler().add({**fragment, "data": "AAAA!"})


@pytest.mark.parametrize("field", ["type", "carries", "id", "index", "total", "data"])
def test_a_fragment_without_a_field_is_refused(field):
    fragment = good()[0]
    del fragment[field]
    with pytest.raises(ValueError):
        FragmentAssembler().add(fragment)


def test_an_extra_field_is_refused():
    with pytest.raises(ValueError):
        FragmentAssembler().add({**good()[0], "more": 1})


@pytest.mark.parametrize(
    "change",
    [{"id": "a" * 64}, {"total": 4}, {"carries": "EPOCH_REPORT"}, {"index": 2}, {"index": 0}],
    ids=str,
)
def test_a_second_fragment_must_continue_the_first(change):
    fragments = good()
    assembler = FragmentAssembler()
    assert assembler.add(fragments[0]) is None
    with pytest.raises(ValueError):
        assembler.add({**fragments[1], **change})


def test_altered_data_is_found_at_the_end():
    fragments = good(2)
    fragments[1]["data"] = base64.b64encode(b"z" * 5).decode()
    with pytest.raises(ValueError, match="DIGEST"):
        assembled(fragments)


def test_an_assembler_can_be_used_again():
    assembler = FragmentAssembler()
    assert not assembler.in_progress
    first, second = good(2)
    assert assembler.add(first) is None
    assert assembler.in_progress
    assert assembler.add(second) is not None
    assert not assembler.in_progress
    assert assembler.add(first) is None


def test_the_digest_is_of_the_payload():
    payload = b"abc"
    assert split_payload("EPOCH_REPORT", payload)[0]["id"] == hashlib.sha256(payload).hexdigest()


# On a connection.

@pytest.mark.parametrize("use", ["send", "enqueue"])
def test_a_large_message_arrives_as_one(use):
    left, right = pair()
    message = {"type": "EPOCH_CLOSURE", "closure": LARGE}
    threading.Thread(target=getattr(left, use), args=(message,), daemon=True).start()
    assert right.receive() == message
    left.close()
    right.close()


@pytest.mark.parametrize("use", ["send", "enqueue"])
def test_a_large_message_of_another_type_is_refused_and_the_connection_stays(use):
    left, right = pair()
    with pytest.raises(ValueError):
        getattr(left, use)({"type": "VOTE", "data": LARGE})
    assert left.connected
    left.close()
    right.close()


def test_a_message_inside_a_fragmented_one_is_a_fault():
    left, right = pair()
    fragments = split_payload("EPOCH_CLOSURE", b"{" * (FRAGMENT_DATA_SIZE + 1))
    send_behind(left.connection, fragments[0], {"type": "VOTE"})
    with pytest.raises(ValueError):
        right.receive()
    left.close()
    right.close()


def test_a_whole_payload_that_is_not_a_message_is_a_fault():
    left, right = pair()
    SecureTransport.send(left.connection, split_payload("EPOCH_CLOSURE", b"[1]")[0])
    with pytest.raises(ValueError):
        right.receive()
    left.close()
    right.close()


def test_what_is_received_together_stops_at_a_piece_of_a_message():
    # Nothing waits for the rest of a large message.
    left, right = pair()
    fragments = split_payload("EPOCH_CLOSURE", b"{" * (FRAGMENT_DATA_SIZE + 1))
    send_behind(left.connection, {"type": "A"}, {"type": "B"}, fragments[0], {"type": "C"})
    first = right.receive()
    frames = iter([True, True, True])
    wrapper = _WithFrameAvailable(right.connection, frames)
    right.connection = wrapper
    messages, broken = right._received_together(first)
    assert [m["type"] for m in messages] == ["A", "B"]
    assert not broken
    assert right._assembler.in_progress
    left.close()
    right.close()


class _WithFrameAvailable:
    def __init__(self, connection, answers):
        self._connection = connection
        self._answers = answers

    def frame_available(self):
        return next(self._answers)

    def __getattr__(self, name):
        return getattr(self._connection, name)


def test_messages_leave_in_the_order_of_the_calls():
    left, right = pair()
    for number in range(200):
        left.enqueue({"type": "T", "n": number})
    assert [right.receive()["n"] for _ in range(200)] == list(range(200))
    left.close()
    right.close()


def test_enqueue_does_not_wait_for_a_peer_that_does_not_read():
    left, right = pair()
    started = time.monotonic()
    for _ in range(50):
        left.enqueue({"type": "T", "data": "x" * 1_000_000})
    assert time.monotonic() - started < 5
    assert left._queued_bytes > 0
    left.close()
    right.close()


def test_a_peer_too_far_behind_loses_the_queue_not_the_node(monkeypatch):
    monkeypatch.setattr(PeerConnection, "MAX_QUEUED_BYTES", 100_000)
    left, right = pair()
    with pytest.raises(ConnectionError):
        for _ in range(1_000):
            left.enqueue({"type": "T", "data": "x" * 50_000})
    left.close()
    right.close()


def test_the_bound_counts_only_what_is_still_queued(monkeypatch):
    monkeypatch.setattr(PeerConnection, "MAX_QUEUED_BYTES", 100_000)
    left, right = pair()
    for number in range(100):
        left.enqueue({"type": "T", "n": number, "data": "x" * 10_000})
        assert right.receive()["n"] == number
        assert left.flush(5)
    left.close()
    right.close()


def test_a_failed_write_closes_and_tells():
    left, right = pair()
    told = []
    left.on_disconnect = told.append
    right.close()
    deadline = time.monotonic() + 5
    while not told and time.monotonic() < deadline:
        try:
            left.enqueue({"type": "T", "data": "x" * 100_000})
        except ConnectionError:
            pass
        time.sleep(0.01)
    assert told == [left]
    assert not left.connected


def test_enqueue_after_close_is_refused():
    left, right = pair()
    left.close()
    with pytest.raises(ConnectionError):
        left.enqueue({"type": "T"})
    right.close()


def test_close_ends_the_writer_and_empties_the_queue():
    left, right = pair()
    for _ in range(50):
        left.enqueue({"type": "T", "data": "x" * 1_000_000})
    writer = left._writer
    left.close()
    writer.join(5)
    assert not writer.is_alive()
    assert left._queued_bytes == 0
    right.close()


def test_close_ends_an_idle_writer():
    left, right = pair()
    left.enqueue({"type": "T"})
    assert right.receive()["type"] == "T"
    assert left.flush(5)
    writer = left._writer
    left.close()
    writer.join(5)
    assert not writer.is_alive()
    right.close()


def test_flush_waits_for_the_queue():
    left, right = pair()
    assert left.flush(0.0)
    left.enqueue({"type": "T", "data": "x" * 5_000_000})
    assert not left.flush(0.05)
    threading.Timer(0.3, right.receive).start()
    assert left.flush(10)
    left.close()
    right.close()


def test_flush_on_a_closed_connection_with_nothing_queued():
    left, right = pair()
    left.close()
    assert left.flush(1)
    right.close()


# On the node.

SENDER = Identity.create()
GENESIS = State({SENDER.identity_id: 10**9})
MEMBERS = sorted((Identity.create() for _ in range(4)), key=lambda member: member.public_key)
COMMITTEE = Committee.create([member.public_key for member in MEMBERS], 1, GENESIS)
SIGNERS = [Identity.create() for _ in range(3)]
GOVERNANCE = Governance(tuple(sorted(signer.public_key for signer in SIGNERS)), 2)


def wait_until(condition, seconds=30.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return condition()


def make_nodes(tmp_path, **options):
    nodes = [
        Node(
            f"q{index}-{tmp_path.name[-8:].replace('_', '-')}",
            GENESIS,
            quorum=QuorumConfig(
                COMMITTEE,
                member,
                tmp_path / f"{index}.sqlite",
                create=True,
                governance=GOVERNANCE,
                **options,
            ),
        )
        for index, member in enumerate(MEMBERS)
    ]
    for node in nodes:
        node.start()
    for index, low in enumerate(nodes):
        for high in nodes[index + 1:]:
            host, port = high.address()
            assert low.connect_peer(Peer(node_id=high.node_id, host=host, port=port))
    assert wait_until(lambda: all(len(node.peer_connections) == 3 for node in nodes))
    return nodes


def test_a_peer_that_stops_reading_does_not_stop_a_certificate(tmp_path):
    nodes = make_nodes(tmp_path)
    try:
        # Member 3 is alive and connected, but reads nothing from member 0. The other two
        # are enough for the quorum, and must not wait for it.
        stuck = nodes[0].peer_connections[nodes[3].node_id]
        original = stuck.connection.sendall
        release = threading.Event()

        def never(frame):
            release.wait(60)
            original(frame)

        stuck.connection.sendall = never
        started = time.monotonic()
        spend = SignedTransfer.create(SENDER, Transfer(SENDER.identity_id, "bob", 1, 0))
        assert nodes[0].submit(spend)
        assert wait_until(lambda: spend.transfer in nodes[0].local_events, 10)
        assert wait_until(lambda: spend.transfer in nodes[1].local_events, 10)
        assert time.monotonic() - started < 10
        release.set()
    finally:
        for node in nodes:
            node.stop()


@pytest.mark.slow
def test_an_epoch_larger_than_a_frame_can_close(tmp_path):
    # This is the limit of about 12 000 events that used to stop an epoch for good.
    count = 16_000
    signed = [
        SignedTransfer.create(SENDER, Transfer(SENDER.identity_id, "bob", 1, nonce))
        for nonce in range(count)
    ]
    nodes = make_nodes(tmp_path)

    try:
        for node in nodes:
            store = node._quorum._store
            with store.group():
                for one in signed:
                    assert store.record_vote(one.transfer, one)

        size = len(json.dumps([[one.transfer.canonical().decode(), one.public_key.hex(), one.signature.hex()] for one in signed])) * 3
        assert size > MAX_MESSAGE_SIZE

        keys = [member.public_key for member in MEMBERS]
        change = EpochChange.create(COMMITTEE, keys, 1, GOVERNANCE, SIGNERS[:2])
        assert nodes[0].propose_epoch_change(change)
        assert wait_until(lambda: all(node.committee_epoch == 1 for node in nodes), 300)

        # The locks went across: the alternative of a reported event gets no vote.
        other = SignedTransfer.create(SENDER, Transfer(SENDER.identity_id, "carol", 1, 5))
        assert not nodes[1].submit(other)
    finally:
        for node in nodes:
            node.stop()
