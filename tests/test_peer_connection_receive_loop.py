import socket
import threading

import pytest

from network.peer_connection import PeerConnection


class FakeSocket:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def make_connection():
    peer = PeerConnection("node-A", "127.0.0.1", 12345)
    sock = FakeSocket()
    peer.connection = sock
    disconnected = []
    peer.on_disconnect = lambda connection: disconnected.append(connection)
    peer.receive = lambda: {"type": "INVALID"}
    return peer, sock, disconnected


def test_invalid_message_closes_connection_and_notifies_disconnect():
    peer, sock, disconnected = make_connection()

    def handler(message, connection):
        raise ValueError("invalid peer message")

    peer.receive_loop(handler)

    assert sock.closed
    assert peer.connection is None
    assert disconnected == [peer]


def test_unexpected_handler_error_cleans_up_and_is_reraised():
    peer, sock, disconnected = make_connection()

    def handler(message, connection):
        raise RuntimeError("internal failure")

    with pytest.raises(RuntimeError, match="internal failure"):
        peer.receive_loop(handler)

    assert sock.closed
    assert peer.connection is None
    assert disconnected == [peer]

def test_callback_error_propagates_after_connection_is_closed():
    peer, sock, disconnected = make_connection()
    callback_saw_closed_socket = []

    def failing_callback(connection):
        callback_saw_closed_socket.append(sock.closed)
        raise RuntimeError("disconnect callback failure")

    peer.on_disconnect = failing_callback

    def invalid_handler(message, connection):
        raise ValueError("invalid peer message")

    with pytest.raises(RuntimeError, match="disconnect callback failure"):
        peer.receive_loop(invalid_handler)

    assert sock.closed
    assert peer.connection is None
    assert callback_saw_closed_socket == [True]


def _frame(payload: bytes) -> bytes:
    return len(payload).to_bytes(4, "big") + payload


MALFORMED_FRAMES = {
    "invalid json": _frame(b"{not json"),
    "invalid utf-8": _frame(b"\xff\xfe"),
    "not an object": _frame(b"[1, 2]"),
    # Python refuses to parse this integer with a plain ValueError, which is not
    # a JSONDecodeError.
    "integer too long": _frame(b'{"a":1' + b"0" * 5000 + b"}"),
    # RecursionError, which is not a ValueError at all.
    "nested too deeply": _frame(b"[" * 200000),
    "length zero": (0).to_bytes(4, "big"),
    "length over the limit": (2**32 - 1).to_bytes(4, "big"),
}


@pytest.mark.parametrize("name", MALFORMED_FRAMES)
def test_malformed_frame_closes_connection_and_notifies_disconnect(name):
    # Without this the reader thread dies while the connection still counts as
    # connected: nothing reads from it again, and nothing reconnects.
    remote, local = socket.socketpair()
    peer = PeerConnection("node-A", "127.0.0.1", 12345)
    peer.connection = local
    disconnected = []
    peer.on_disconnect = lambda connection: disconnected.append(connection)
    handled = []

    def send():
        try:
            remote.sendall(MALFORMED_FRAMES[name])
        except OSError:
            pass  # The loop refused the frame before reading all of it.

    sender = threading.Thread(target=send)
    sender.start()

    try:
        peer.receive_loop(lambda message, connection: handled.append(message))
    finally:
        remote.close()
        sender.join(timeout=10)

    assert handled == []
    assert peer.connected is False
    assert disconnected == [peer]


def test_message_before_a_malformed_frame_is_still_handled():
    remote, local = socket.socketpair()
    peer = PeerConnection("node-A", "127.0.0.1", 12345)
    peer.connection = local
    handled = []
    remote.sendall(_frame(b'{"type":"PING"}') + _frame(b"{not json"))

    peer.receive_loop(lambda message, connection: handled.append(message))
    remote.close()

    assert handled == [{"type": "PING"}]
    assert peer.connected is False


def test_unexpected_receive_error_cleans_up_and_is_reraised():
    # As for the handler: a bug on this side is not hidden, but leaves no zombie.
    peer, sock, disconnected = make_connection()

    def receive():
        raise RuntimeError("internal failure")

    peer.receive = receive

    with pytest.raises(RuntimeError, match="internal failure"):
        peer.receive_loop(lambda message, connection: None)

    assert sock.closed
    assert peer.connection is None
    assert disconnected == [peer]
