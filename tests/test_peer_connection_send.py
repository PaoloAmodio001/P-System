import socket
import threading
import time

from network.node_tls_identity import get_node_tls_config
from network.peer_connection import PeerConnection
from network.secure_transport import SecureTransport

import pytest


SENDERS = 4
FRAMES_EACH = 20


class OverlapSocket:
    """Records how many sendall calls run at the same time."""

    def __init__(self):
        self.lock = threading.Lock()
        self.active = 0
        self.max_active = 0

    def sendall(self, data):
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        time.sleep(0.005)
        with self.lock:
            self.active -= 1


class BlockedSocket:
    """A sendall that stays blocked, as with a peer that does not read."""

    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.closed = False

    def sendall(self, data):
        self.entered.set()
        assert self.release.wait(timeout=5)

    def close(self):
        self.closed = True
        self.release.set()


def connection_on(sock):
    peer = PeerConnection("node-A", "127.0.0.1", 12345)
    peer.connection = sock
    return peer


def _send_from_threads(peer, payload_size):
    start = threading.Barrier(SENDERS)
    errors = []

    def sender(index):
        try:
            start.wait(timeout=5)
            for sequence in range(FRAMES_EACH):
                peer.send(
                    {
                        "sender": index,
                        "sequence": sequence,
                        "padding": "x" * payload_size,
                    }
                )
        except Exception as error:
            errors.append(error)

    threads = [
        threading.Thread(target=sender, args=(index,), daemon=True)
        for index in range(SENDERS)
    ]
    for thread in threads:
        thread.start()
    return threads, errors


def _read_all_frames(reader, payload_size):
    received = []
    for _ in range(SENDERS * FRAMES_EACH):
        message = SecureTransport.receive(reader)
        assert len(message["padding"]) == payload_size
        received.append((message["sender"], message["sequence"]))
    return received


def _assert_every_frame_arrived_in_order(received):
    for index in range(SENDERS):
        assert [
            sequence for sender, sequence in received if sender == index
        ] == list(range(FRAMES_EACH))


def test_concurrent_sends_never_overlap():
    sock = OverlapSocket()
    threads, errors = _send_from_threads(connection_on(sock), 8)

    for thread in threads:
        thread.join(timeout=10)

    assert errors == []
    assert sock.max_active == 1


def test_frames_stay_whole_on_a_real_socket():
    # Larger than the socket buffer, so that sendall is split into several writes.
    payload_size = 512 * 1024
    writer, reader = socket.socketpair()
    reader.settimeout(10)

    try:
        threads, errors = _send_from_threads(connection_on(writer), payload_size)
        received = _read_all_frames(reader, payload_size)

        for thread in threads:
            thread.join(timeout=10)

        assert errors == []
        _assert_every_frame_arrived_in_order(received)
    finally:
        writer.close()
        reader.close()


def test_frames_stay_whole_on_real_tls():
    # Frames over one TLS record (16 KB), the sizes that certificates can reach.
    payload_size = 256 * 1024
    listener = socket.create_server(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    accepted = {}

    def accept():
        raw, _ = listener.accept()
        accepted["reader"] = SecureTransport.wrap_server(
            raw,
            SecureTransport.create_server_context(get_node_tls_config("send-B")),
        )

    acceptor = threading.Thread(target=accept, daemon=True)
    acceptor.start()

    config = get_node_tls_config("send-A")
    writer = SecureTransport.wrap_client(
        socket.create_connection(("127.0.0.1", port), timeout=5),
        SecureTransport.create_client_context(config),
        "send-B",
    )
    acceptor.join(timeout=5)
    reader = accepted["reader"]
    reader.settimeout(20)
    writer.settimeout(None)

    try:
        threads, errors = _send_from_threads(connection_on(writer), payload_size)
        received = _read_all_frames(reader, payload_size)

        for thread in threads:
            thread.join(timeout=10)

        assert errors == []
        _assert_every_frame_arrived_in_order(received)
    finally:
        writer.close()
        reader.close()
        listener.close()


def test_send_waiting_for_its_turn_fails_cleanly_after_close():
    sock = BlockedSocket()
    peer = connection_on(sock)
    outcome = []

    def send(name):
        try:
            peer.send({"type": name})
            outcome.append((name, None))
        except Exception as error:
            outcome.append((name, type(error)))

    first = threading.Thread(target=send, args=("first",), daemon=True)
    first.start()
    assert sock.entered.wait(timeout=5)

    second = threading.Thread(target=send, args=("second",), daemon=True)
    second.start()
    time.sleep(0.05)

    # close must not wait for the send lock: it is what frees a blocked send.
    closer = threading.Thread(target=peer.close, daemon=True)
    closer.start()
    closer.join(timeout=2)
    assert not closer.is_alive()

    first.join(timeout=5)
    second.join(timeout=5)

    assert dict(outcome)["second"] is ConnectionError


def test_failed_send_does_not_hold_the_lock():
    class FailingSocket:
        def __init__(self):
            self.calls = 0

        def sendall(self, data):
            self.calls += 1
            raise OSError("broken pipe")

    sock = FailingSocket()
    peer = connection_on(sock)

    for _ in range(2):
        with pytest.raises(OSError):
            peer.send({"type": "PING"})

    assert sock.calls == 2


def test_send_when_not_connected_raises_connection_error():
    peer = PeerConnection("node-A", "127.0.0.1", 12345)

    with pytest.raises(ConnectionError):
        peer.send({"type": "PING"})
