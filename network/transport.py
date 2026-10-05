from __future__ import annotations

import json
import socket
from typing import Optional

from network.secure_transport import SecureTransport, TLSConfig


class TCPTransport:
    """
    Compatibility facade for the P-System network transport.

    New connections MUST use TLS 1.3.  The framing/API remains
    compatible with the previous transport layer.
    """

    def __init__(
        self,
        host: str,
        port: int,
        tls_config: Optional[TLSConfig] = None,
    ):
        self.host = host
        self.port = port
        self.tls_config = tls_config

    def connect(self, peer, node_id: str):
        from network.handshake import Handshake

        if self.tls_config is None:
            raise RuntimeError(
                "P14 TLS CONFIGURATION REQUIRED"
            )

        connection = socket.create_connection(
            peer.address(),
            timeout=2.0,
        )

        try:
            context = SecureTransport.create_client_context(
                self.tls_config
            )

            connection = SecureTransport.wrap_client(
                connection,
                context,
                self.tls_config.server_hostname,
            )

            SecureTransport.send(
                connection,
                Handshake(
                    node_id=node_id,
                    host=self.host,
                    port=self.port,
                ).encode(),
            )

            response = SecureTransport.receive(connection)
            handshake = Handshake.decode(response)

            if handshake.node_id == node_id:
                raise ValueError(
                    "INVALID PEER IDENTITY"
                )

            return connection, handshake

        except Exception:
            connection.close()
            raise

    def send(self, peer, message: dict) -> None:
        if self.tls_config is None:
            raise RuntimeError(
                "P14 TLS CONFIGURATION REQUIRED"
            )

        connection = socket.create_connection(
            peer.address(),
            timeout=2.0,
        )

        try:
            context = SecureTransport.create_client_context(
                self.tls_config
            )

            connection = SecureTransport.wrap_client(
                connection,
                context,
                self.tls_config.server_hostname,
            )

            SecureTransport.send(
                connection,
                message,
            )
        finally:
            connection.close()

    @staticmethod
    def send_connection(connection, message: dict) -> None:
        SecureTransport.send(
            connection,
            message,
        )

    @staticmethod
    def receive(connection) -> dict:
        return SecureTransport.receive(
            connection
        )

    @staticmethod
    def _read_exact(connection, size: int) -> bytes:
        return SecureTransport._read_exact(
            connection,
            size,
        )
