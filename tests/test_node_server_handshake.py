import socket
import ssl
import threading
import time

import pytest

from tests.node_helpers import standalone_node
from network.node import Node
from network.node_tls_identity import get_node_tls_config
from network.peer import Peer
from network.secure_transport import SecureTransport


def _open_tls_connection(node: Node, client_id: str) -> ssl.SSLSocket:
    # A client with a valid certificate: TLS is mutual, so this is what a
    # malicious committee member can do, and an outsider cannot.
    context = SecureTransport.create_client_context(
        get_node_tls_config(client_id)
    )
    connection = socket.create_connection(node.address(), timeout=10.0)
    return SecureTransport.wrap_client(connection, context, node.node_id)


def _wait_until(condition, seconds: float = 5.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return condition()


def _closed_by_server(connection: ssl.SSLSocket) -> bool:
    try:
        return connection.recv(1) == b""
    except TimeoutError:
        return False
    except OSError:
        # The server closes without a TLS close_notify.
        return True


# A handshake has its own thread, so an error there no longer stops accepting
# peers. It must still be handled: an unhandled one fails this test.
@pytest.mark.filterwarnings("error::pytest.PytestUnhandledThreadExceptionWarning")
def test_deeply_nested_handshake_does_not_stop_accepting_peers():
    server = standalone_node("handshake-server")
    honest = standalone_node("handshake-honest")
    server.start()
    honest.start()
    attacker = _open_tls_connection(server, "handshake-attacker")

    try:
        # json.loads raises RecursionError, which is not a ValueError.
        payload = b"[" * 200000
        attacker.sendall(len(payload).to_bytes(4, "big") + payload)

        assert honest.connect_peer(
            Peer(server.node_id, server.host, server.port)
        )
        assert server._server_controller.thread.is_alive()
        assert _closed_by_server(attacker)
    finally:
        attacker.close()
        honest.stop()
        server.stop()


def _server_closed_within(connection: socket.socket, seconds: float) -> bool:
    connection.settimeout(seconds)
    try:
        return connection.recv(1) == b""
    except TimeoutError:
        return False
    except OSError:
        return True


def test_silent_connection_does_not_block_an_honest_peer():
    # No certificate is needed: the connection never starts TLS.
    server = standalone_node("silent-server")
    honest = standalone_node("silent-honest")
    server.start()
    honest.start()
    silent = socket.create_connection(server.address())

    try:
        assert honest.connect_peer(
            Peer(server.node_id, server.host, server.port)
        )
    finally:
        silent.close()
        honest.stop()
        server.stop()


def test_silent_connection_is_closed_at_the_deadline():
    server = standalone_node("deadline-server")
    server._server_controller.HANDSHAKE_TIMEOUT = 0.2
    server.start()
    silent = socket.create_connection(server.address())

    try:
        assert _server_closed_within(silent, 5.0)
    finally:
        silent.close()
        server.stop()


def test_slowly_sent_bytes_do_not_extend_the_deadline():
    # The deadline is for the whole handshake, not for each read.
    server = standalone_node("slow-server")
    server._server_controller.HANDSHAKE_TIMEOUT = 0.5
    server.start()
    slow = socket.create_connection(server.address())
    slow.settimeout(0.1)
    deadline = time.monotonic() + 5.0
    closed = False

    try:
        # The header of a TLS record of 16 KB, whose body never ends. Each byte is
        # valid and each read succeeds, so only a deadline on the whole handshake
        # closes this.
        slow.sendall(b"\x16\x03\x01\x40\x00")

        while not closed and time.monotonic() < deadline:
            try:
                slow.sendall(b"\x00")
                closed = slow.recv(1) == b""
            except TimeoutError:
                pass
            except OSError:
                closed = True

        assert closed
    finally:
        slow.close()
        server.stop()


def test_with_no_place_left_the_one_waiting_longest_goes():
    server = standalone_node("limit-server")
    honest = standalone_node("limit-honest")
    server._server_controller.MAX_PENDING_HANDSHAKES = 1
    server.start()
    honest.start()
    peer = Peer(server.node_id, server.host, server.port)
    holder = socket.create_connection(server.address())

    try:
        assert _wait_until(lambda: len(server._server_controller._pending) == 1)
        # The silent connection goes, and an honest peer gets its place.
        assert honest.open_peer_connection(peer)
        assert _server_closed_within(holder, 5.0)
    finally:
        holder.close()
        honest.stop()
        server.stop()


def test_stop_ends_a_handshake_in_progress():
    server = standalone_node("stop-server")
    server.start()
    controller = server._server_controller
    silent = socket.create_connection(server.address())

    try:
        assert _wait_until(lambda: len(controller._pending) == 1)
        threads = list(controller._pending.values())
        server.stop()
        assert not any(thread.is_alive() for thread in threads)
        assert _server_closed_within(silent, 5.0)
    finally:
        silent.close()


class _PeerWithNestedReply:
    """A malicious peer on the other side of a connection the node opens."""

    def __init__(self, node_id: str):
        self.context = SecureTransport.create_server_context(
            get_node_tls_config(node_id)
        )
        self.listener = socket.create_server(("127.0.0.1", 0))
        self.listener.settimeout(0.05)
        self.peer = Peer(node_id, "127.0.0.1", self.listener.getsockname()[1])
        self.replies = 0
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self._serve, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stopped.set()
        self.thread.join(timeout=5.0)
        self.listener.close()

    def _serve(self):
        while not self.stopped.is_set():
            try:
                raw, _ = self.listener.accept()
            except TimeoutError:
                continue

            try:
                with self.context.wrap_socket(raw, server_side=True) as connection:
                    SecureTransport.receive(connection)
                    payload = b"[" * 200000
                    connection.sendall(len(payload).to_bytes(4, "big") + payload)
                    self.replies += 1
                    # Open until the client closes: the frame is the only cause.
                    connection.settimeout(5.0)
                    connection.recv(1)
            except OSError:
                pass


def test_deeply_nested_handshake_reply_fails_the_connection_attempt():
    client = standalone_node("reply-client-direct")

    with _PeerWithNestedReply("reply-evil-direct") as evil:
        assert client.connect_peer(evil.peer) is False
        assert evil.replies == 1
        assert client.peer_connections.get(evil.peer.node_id) is None
        assert client._reconnect_state[evil.peer.node_id].attempts == 1


@pytest.mark.filterwarnings("error::pytest.PytestUnhandledThreadExceptionWarning")
def test_deeply_nested_handshake_reply_does_not_stop_reconnecting():
    client = standalone_node("reply-client-loop")
    client.RECONNECT_BASE_DELAY = 0.01

    with _PeerWithNestedReply("reply-evil-loop") as evil:
        client.add_peer(evil.peer)
        client.start()

        try:
            # A second reply proves that the thread survived the first.
            assert _wait_until(lambda: evil.replies >= 2)
            assert client._reconnect_thread.is_alive()
        finally:
            client.stop()
