"""Worker process for tests/test_tls_duplex.py: two PeerConnections on real TLS.

Both sides send as soon as the TLS handshake ends, with a reader running. Run as a script,
because what goes wrong on a shared TLS socket can be a crash or a hang.
"""

import socket
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from network.handshake import Handshake  # noqa: E402
from network.node_tls_identity import get_node_tls_config  # noqa: E402
from network.peer_connection import PeerConnection  # noqa: E402
from network.secure_transport import SecureTransport  # noqa: E402

COUNT = int(sys.argv[1])
SIZE = int(sys.argv[2])


def tls_pair():
    listener = socket.create_server(("127.0.0.1", 0))
    accepted = {}

    def accept():
        raw, _ = listener.accept()
        accepted["socket"] = SecureTransport.wrap_server(
            raw,
            SecureTransport.create_server_context(get_node_tls_config("duplex-b")),
        )

    thread = threading.Thread(target=accept)
    thread.start()
    client = SecureTransport.wrap_client(
        socket.create_connection(listener.getsockname(), timeout=5),
        SecureTransport.create_client_context(get_node_tls_config("duplex-a")),
        "duplex-b",
    )
    thread.join()
    client.settimeout(None)
    accepted["socket"].settimeout(None)
    return client, accepted["socket"]


def adopt(sock, node_id):
    return PeerConnection.adopt(node_id, sock, Handshake(node_id, "127.0.0.1", 1))


def main() -> None:
    left, right = (adopt(sock, name) for sock, name in zip(tls_pair(), "ab"))
    message = {"type": "X", "data": "x" * SIZE}
    errors = []
    received = [0, 0]

    def read(connection, slot):
        try:
            for _ in range(COUNT):
                assert connection.receive() == message
                received[slot] += 1
        except BaseException as error:
            errors.append(repr(error))

    def write(connection):
        try:
            for _ in range(COUNT):
                connection.send(message)
        except BaseException as error:
            errors.append(repr(error))

    threads = [
        threading.Thread(target=read, args=(left, 0), daemon=True),
        threading.Thread(target=read, args=(right, 1), daemon=True),
        threading.Thread(target=write, args=(left,), daemon=True),
        threading.Thread(target=write, args=(right,), daemon=True),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    if errors or received != [COUNT, COUNT]:
        print(errors[:2], received)
        sys.exit(1)

    print("OK")


main()
