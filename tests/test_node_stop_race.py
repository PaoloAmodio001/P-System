"""A connection must not outlive Node.stop.

stop closes the connections it finds and stops the server. If it closes them first,
a handshake still in progress can publish a connection after that, and nothing ever
closes it: its reader goes on with the node stopped. So the server stops first.
"""

import socket
import threading
import time

from network.handshake import Handshake
from tests.node_helpers import standalone_node
from network.node import Node
from network.node_tls_identity import get_node_tls_config
from network.secure_transport import SecureTransport


def _open_tls(server: Node, client_id: str):
    context = SecureTransport.create_client_context(get_node_tls_config(client_id))
    raw = socket.create_connection(server.address(), timeout=10.0)
    return SecureTransport.wrap_client(raw, context, server.node_id)


def _hello(client_id: str) -> dict:
    return Handshake(node_id=client_id, host="127.0.0.1", port=1).encode()


def _closed_by_server(connection, seconds: float = 3.0) -> bool:
    # Read to the end: the reply to the handshake may be there first.
    connection.settimeout(seconds)
    try:
        while connection.recv(4096):
            pass
    except TimeoutError:
        return False
    except OSError:
        # The server closes without a TLS close_notify.
        return True
    return True


def _run_when_server_stops(node: Node, action) -> None:
    # Both orders call this once: it marks the moment, whatever comes before it.
    controller = node._server_controller
    real_stop = controller.stop

    def stop():
        controller.stop = real_stop
        action()
        real_stop()

    controller.stop = stop


def _assert_nothing_outlives_stop(node: Node, client_id: str, connection) -> None:
    assert client_id not in node.peer_connections
    assert _closed_by_server(connection)


def test_peer_finishing_its_handshake_during_stop_does_not_stay_connected():
    server = standalone_node("stop-race-a")
    server.start()
    client_id = "stop-race-client-a"
    connection = _open_tls(server, client_id)

    try:
        # Sent only when the server is about to stop: as a peer whose handshake is
        # simply in flight, with nothing in the node slowed down.
        _run_when_server_stops(
            server,
            lambda: SecureTransport.send(connection, _hello(client_id)),
        )
        server.stop()
        # Whatever the handshake thread was doing has had time to finish.
        time.sleep(0.2)

        _assert_nothing_outlives_stop(server, client_id, connection)
    finally:
        connection.close()
        server.stop()


def test_connection_being_published_during_stop_does_not_outlive_it():
    # The narrow case: the handshake is over, and only publishing it is left. This
    # one fixes the order of the two steps in Node.stop, because the server cannot
    # refuse a connection that has already passed its check.
    server = standalone_node("stop-race-b")
    server.start()
    client_id = "stop-race-client-b"
    reached, release = threading.Event(), threading.Event()
    real_register = server._register_peer_connection

    def register(node_id, peer_connection):
        reached.set()
        assert release.wait(timeout=5)
        return real_register(node_id, peer_connection)

    server._register_peer_connection = register
    connection = _open_tls(server, client_id)

    try:
        SecureTransport.send(connection, _hello(client_id))
        assert reached.wait(timeout=5)

        _run_when_server_stops(server, release.set)
        server.stop()
        time.sleep(0.2)

        _assert_nothing_outlives_stop(server, client_id, connection)
    finally:
        release.set()
        connection.close()
        server.stop()
