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
