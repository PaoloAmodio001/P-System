from __future__ import annotations

import socket
import threading

from network.handshake import Handshake
from network.peer import Peer
from network.secure_transport import SecureTransport, TLSConfig


class PeerConnection:
    def __init__(
        self,
        node_id: str,
        host: str,
        port: int,
    ):
        self.node_id = node_id
        self.host = host
        self.port = port
        self.connection = None
        self.remote_handshake = None
        self.tls_config = None
        self.on_disconnect = None
        self.initiated_locally = True
        self._send_lock = threading.Lock()

    @property
    def connected(self) -> bool:
        return self.connection is not None

    def connect(
        self,
        peer: Peer,
        tls_config: TLSConfig,
    ) -> Handshake:
        if self.connected:
            raise RuntimeError("ALREADY CONNECTED")

        connection = socket.create_connection(
            peer.address(),
            timeout=2.0,
        )

        try:
            context = SecureTransport.create_client_context(
                tls_config
            )

            connection = SecureTransport.wrap_client(
                connection,
                context,
                peer.node_id,
            )

            SecureTransport.send(
                connection,
                Handshake(
                    node_id=self.node_id,
                    host=self.host,
                    port=self.port,
                ).encode(),
            )

            response = SecureTransport.receive(connection)
            handshake = Handshake.decode(response)

            if handshake.node_id == self.node_id:
                raise ValueError("INVALID PEER IDENTITY")

            # Il timeout breve serve solo per stabilire la connessione.
            # La connessione TLS persistente deve poter restare inattiva.
            connection.settimeout(None)

            self.connection = connection
            self.remote_handshake = handshake
            self.tls_config = tls_config

            return handshake

        except Exception:
            connection.close()
            raise

    @classmethod
    def adopt(
        cls,
        node_id: str,
        connection,
        handshake: Handshake,
    ) -> "PeerConnection":
        peer_connection = cls(
            node_id=node_id,
            host=handshake.host,
            port=handshake.port,
        )

        peer_connection.connection = connection
        peer_connection.remote_handshake = handshake
        peer_connection.initiated_locally = False

        return peer_connection

    def send(self, message: dict) -> None:
        # One frame at a time: threads writing together on a TLS socket mix their
        # frames and can crash the process. close does not take this lock, because
        # closing is what frees a send blocked on a peer that does not read.
        with self._send_lock:
            connection = self.connection

            if connection is None:
                raise ConnectionError("PEER NOT CONNECTED")

            SecureTransport.send(
                connection,
                message,
            )

    def receive(self) -> dict:
        if not self.connected:
            raise ConnectionError("PEER NOT CONNECTED")

        return SecureTransport.receive(
            self.connection,
        )

    def receive_loop(self, handler) -> None:
        if not self.connected:
            raise ConnectionError("PEER NOT CONNECTED")

        while self.connected:
            try:
                message = self.receive()
            except (
                ConnectionError,
                OSError,
                TimeoutError,
                ValueError,
                RecursionError,
            ):
                # ValueError and RecursionError: the peer sent a malformed frame.
                self._close_and_notify()
                return
            except Exception:
                self._close_and_notify()
                raise

            try:
                handler(message, self)
            except (ValueError, KeyError, TypeError, IndexError):
                self._close_and_notify()
                return
            except Exception:
                self._close_and_notify()
                raise

    def _close_and_notify(self) -> None:
        self.close()
        callback = self.on_disconnect
        if callback is not None:
            callback(self)

    def close(self) -> None:
        if self.connection is None:
            return

        connection = self.connection
        try:
            # Interrompe anche eventuali recv bloccanti in altri thread.
            shutdown = getattr(connection, "shutdown", None)
            if callable(shutdown):
                try:
                    shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            connection.close()
        finally:
            self.connection = None
            self.remote_handshake = None
            self.tls_config = None
