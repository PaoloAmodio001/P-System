import socket
import threading

from network.handshake import Handshake
from network.peer import Peer
from network.peer_connection import PeerConnection
from network.secure_transport import SecureTransport, TLSConfig


class NodeServer:
    """
    Gestisce esclusivamente il lifecycle TCP di un Node.

    Each handshake has its own thread, a deadline and a place among a limited number.
    With no place left the one waiting longest goes, not the one arriving: an honest handshake
    takes milliseconds and a silent connection waits, so the silent one goes first. Each
    address has a limit of its own, so that it cannot push out the others. To push out an honest
    peer, whoever needs no certificate has to open all the places within its handshake.
    """

    HANDSHAKE_TIMEOUT = 5.0
    MAX_PENDING_HANDSHAKES = 64
    MAX_PENDING_PER_ADDRESS = 16

    def __init__(self, node, tls_config: TLSConfig | None = None):
        self.node = node
        self.tls_config = tls_config
        self.server = None
        self.thread = None
        self.running = False
        # Oldest first, and each with the address it came from.
        self._pending = {}
        self._addresses = {}
        self._pending_lock = threading.Lock()

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

        with self._pending_lock:
            pending = dict(self._pending)

        for guard, thread in pending.items():
            self._shut_down(guard)
            thread.join(timeout=1.0)

        self.server = None
        self.thread = None

    def _serve(self):
        while self.running:
            try:
                connection, source = self.server.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            if self.tls_config is None:
                raise RuntimeError(
                    "P14 TLS CONFIGURATION REQUIRED"
                )

            self._start_handshake(connection, source[0])

    def _make_room(self, address: str) -> None:
        """With the lock held. The next arrival from `address` takes the place of who waited longest."""
        same = [guard for guard, source in self._addresses.items() if source == address]

        if len(same) >= self.MAX_PENDING_PER_ADDRESS:
            oldest = same[0]
        elif len(self._pending) >= self.MAX_PENDING_HANDSHAKES:
            oldest = next(iter(self._pending))
        else:
            return

        self._pending.pop(oldest, None)
        self._addresses.pop(oldest, None)
        self._shut_down(oldest)

    def _start_handshake(self, connection, address: str = "") -> None:
        with self._pending_lock:
            self._make_room(address)

            try:
                guard = connection.dup()
            except OSError:
                connection.close()
                return

            thread = threading.Thread(
                target=self._handshake,
                args=(connection, guard),
                daemon=True,
            )
            self._pending[guard] = thread
            self._addresses[guard] = address

            # Under the lock, so that stop never finds a thread not yet started.
            thread.start()

    def _handshake(self, connection, guard) -> None:
        # The guard shares the connection with the TLS socket and outlives the
        # wrapping. Shutting it down wakes a read at any point of the handshake,
        # so the deadline holds for the whole handshake and not for each read.
        deadline = threading.Timer(
            self.HANDSHAKE_TIMEOUT,
            self._shut_down,
            args=(guard,),
        )
        deadline.daemon = True
        deadline.start()

        try:
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
                return

            # A certificate of the authority names one node. Without this, anyone holding
            # one could take the place of any peer, and the connection to the real one.
            if handshake.node_id not in SecureTransport.peer_names(connection):
                connection.close()
                return

            if SecureTransport.is_revoked(connection, self.tls_config):
                connection.close()
                return

            # From where it connected: a peer may announce all its interfaces or nothing
            # useful. Only the port is its own to say, because the connection came from an
            # ephemeral one.
            self.node.peers.setdefault(
                handshake.node_id,
                Peer(
                    node_id=handshake.node_id,
                    host=connection.getpeername()[0],
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

            # From here the connection may stay idle for as long as it wants.
            deadline.cancel()

            if not self.running:
                connection.close()
                return

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
                return

            threading.Thread(
                target=peer_connection.receive_loop,
                args=(
                    self.node._handle_peer_message,
                    getattr(self.node, "_handle_peer_messages", None),
                ),
                daemon=True,
            ).start()

            self.node._request_certificates(peer_connection)

        except (
            ValueError,
            ConnectionError,
            OSError,
            RecursionError,
        ):
            # RecursionError: a frame with JSON nested too deeply, which is
            # not a ValueError. Nothing a peer sends may end this loop.
            self._close_quietly(connection)
        except Exception:
            self._close_quietly(connection)
            raise
        finally:
            deadline.cancel()

            with self._pending_lock:
                self._pending.pop(guard, None)
                self._addresses.pop(guard, None)

            guard.close()

    @staticmethod
    def _shut_down(connection) -> None:
        try:
            connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    @staticmethod
    def _close_quietly(connection) -> None:
        try:
            connection.close()
        except OSError:
            pass
