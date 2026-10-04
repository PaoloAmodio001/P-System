import socket
import threading

from network.transport import TCPTransport
from network.node_tls_identity import get_node_tls_config
from network.secure_transport import SecureTransport


def test_tcp_transport_sends_and_receives_message():
    server = socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM,
    )

    server.bind(("127.0.0.1", 0))
    server.listen(1)

    host, port = server.getsockname()

    received = {}

    def server_worker():
        connection, _ = server.accept()

        with connection:
            config = get_node_tls_config("node-A")
            context = SecureTransport.create_server_context(config)
            tls = SecureTransport.wrap_server(
                connection,
                context,
            )
            with tls:
                received.update(
                    SecureTransport.receive(tls)
                )

        server.close()

    thread = threading.Thread(
        target=server_worker,
        daemon=True,
    )

    thread.start()

    client_config = get_node_tls_config("node-A")

    client = TCPTransport(
        "127.0.0.1",
        port,
        tls_config=client_config,
    )

    class LocalPeer:
        def address(self):
            return host, port

    message = {
        "type": "PING",
        "node_id": "node-A",
    }

    client.send(
        LocalPeer(),
        message,
    )

    thread.join(timeout=2)

    assert received == message
