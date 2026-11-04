import socket
import ssl

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


def _closed_by_server(connection: ssl.SSLSocket) -> bool:
    try:
        return connection.recv(1) == b""
    except TimeoutError:
        return False
    except OSError:
        # The server closes without a TLS close_notify.
        return True


def test_deeply_nested_handshake_does_not_stop_accepting_peers():
    server = Node("handshake-server")
    honest = Node("handshake-honest")
    server.start()
    honest.start()
    attacker = _open_tls_connection(server, "handshake-attacker")

    try:
        # json.loads raises RecursionError, which is not a ValueError.
        payload = b"[" * 200000
        attacker.sendall(len(payload).to_bytes(4, "big") + payload)

        # The server handles one handshake at a time, so this one comes after
        # the frame above has been handled.
        assert honest.connect_peer(
            Peer(server.node_id, server.host, server.port)
        )
        assert server._server_controller.thread.is_alive()
        assert _closed_by_server(attacker)
    finally:
        attacker.close()
        honest.stop()
        server.stop()
