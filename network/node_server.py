import socket
import threading

from network.handshake import Handshake
from network.peer import Peer
from network.peer_connection import PeerConnection
from network.secure_transport import SecureTransport, TLSConfig


class NodeServer:
    """Gestisce esclusivamente il lifecycle TCP di un Node."""

    def __init__(self, node, tls_config: TLSConfig | None = None):
        self.node = node
        self.tls_config = tls_config
        self.server = None
        self.thread = None
        self.running = False

    def start(self):
        if self.running:
            return

        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((self.node.host, self.node.port))
        self.server.listen()
        self.server.settimeout(0.2)

        self.node.port = self.server.getsockname()[1]
        self.running = True

        self.thread = threading.Thread(
            target=self._serve,
            daemon=True,
        )
        self.thread.start()

    def stop(self):
        self.running = False

        if self.server is not None:
            try:
                self.server.close()
            except OSError:
                pass

        if self.thread is not None:
            self.thread.join(timeout=1.0)

        self.server = None
        self.thread = None

    def _serve(self):
        while self.running:
            try:
                connection, _ = self.server.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            try:
                if self.tls_config is None:
                    raise RuntimeError(
                        "P14 TLS CONFIGURATION REQUIRED"
                    )

                context = SecureTransport.create_server_context(
                    self.tls_config
                )

                connection = SecureTransport.wrap_server(
                    connection,
                    context,
                )

                message = SecureTransport.receive(
                    connection
                )

                handshake = Handshake.decode(message)

                if handshake.node_id == self.node.node_id:
                    connection.close()
                    continue

                self.node.peers.setdefault(
                    handshake.node_id,
                    Peer(
                        node_id=handshake.node_id,
                        host=handshake.host,
                        port=handshake.port,
                    ),
                )

                SecureTransport.send(
                    connection,
                    Handshake(
                        node_id=self.node.node_id,
                        host=self.node.host,
                        port=self.node.port,
                    ).encode(),
                )

                peer_connection = PeerConnection.adopt(
                    self.node.node_id,
                    connection,
                    handshake,
                )

                peer_connection.on_disconnect = (
                    self.node._peer_disconnected
                )

                if not self.node._register_peer_connection(
                    handshake.node_id,
                    peer_connection,
                ):
                    peer_connection.close()
                    continue

                threading.Thread(
                    target=peer_connection.receive_loop,
                    args=(self.node._handle_peer_message,),
                    daemon=True,
                ).start()

            except (ValueError, ConnectionError, OSError):
                try:
                    connection.close()
                except OSError:
                    pass
