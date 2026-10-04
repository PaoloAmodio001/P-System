from __future__ import annotations

import socket

from network.handshake import Handshake
from network.peer import Peer
from network.transport import TCPTransport


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
        self.on_disconnect = None

    @property
    def connected(self) -> bool:
        return self.connection is not None

    def connect(self, peer: Peer) -> Handshake:
        if self.connected:
            raise RuntimeError("ALREADY CONNECTED")

        connection = socket.create_connection(
            peer.address(),
            timeout=2.0,
        )

        try:
            TCPTransport.send_connection(
                connection,
                Handshake(
                    node_id=self.node_id,
                    host=self.host,
                    port=self.port,
                ).encode(),
            )

            response = TCPTransport.receive(connection)
            handshake = Handshake.decode(response)

            if handshake.node_id == self.node_id:
                raise ValueError("INVALID PEER IDENTITY")

            self.connection = connection
            self.remote_handshake = handshake

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

        return peer_connection

    def send(self, message: dict) -> None:
        if not self.connected:
            raise ConnectionError("PEER NOT CONNECTED")

        TCPTransport.send_connection(
            self.connection,
            message,
        )

    def receive(self) -> dict:
        if not self.connected:
            raise ConnectionError("PEER NOT CONNECTED")

        return TCPTransport.receive(
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
            ):
                self.close()
                if self.on_disconnect is not None:
                    self.on_disconnect(self)
                return

            handler(message, self)

    def close(self) -> None:
        if self.connection is None:
            return

        try:
            self.connection.close()
        finally:
            self.connection = None
            self.remote_handshake = None
