import socket
import threading

from network.transport import TCPTransport


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
            received.update(
                TCPTransport.receive(connection)
            )

        server.close()

    thread = threading.Thread(
        target=server_worker,
        daemon=True,
    )

    thread.start()

    client = TCPTransport(
        "127.0.0.1",
        port,
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
