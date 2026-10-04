from __future__ import annotations

import json
import socket
import ssl
from dataclasses import dataclass
from typing import Optional


MAX_MESSAGE_SIZE = 16 * 1024 * 1024


@dataclass(frozen=True)
class TLSConfig:
    """
    Explicit trust configuration for X-System node transport.

    certificate:
        Local node certificate.

    private_key:
        Private key belonging to the local certificate.

    ca_file:
        Trust anchor used to authenticate remote node certificates.

    server_hostname:
        TLS hostname/SAN used by the client.  X-System additionally
        verifies the node identity carried by the application handshake.
    """

    certificate: str
    private_key: str
    ca_file: str
    server_hostname: str = "x-system"


class SecureTransport:
    """
    Mandatory TLS 1.3 transport.

    No plaintext fallback is provided.
    """

    MAX_MESSAGE_SIZE = MAX_MESSAGE_SIZE

    @staticmethod
    def create_server_context(config: TLSConfig) -> ssl.SSLContext:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)

        context.minimum_version = ssl.TLSVersion.TLSv1_3
        context.maximum_version = ssl.TLSVersion.TLSv1_3

        context.verify_mode = ssl.CERT_REQUIRED

        context.load_cert_chain(
            certfile=config.certificate,
            keyfile=config.private_key,
        )

        context.load_verify_locations(
            cafile=config.ca_file,
        )

        return context

    @staticmethod
    def create_client_context(config: TLSConfig) -> ssl.SSLContext:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

        context.minimum_version = ssl.TLSVersion.TLSv1_3
        context.maximum_version = ssl.TLSVersion.TLSv1_3

        context.verify_mode = ssl.CERT_REQUIRED
        context.check_hostname = True

        context.load_cert_chain(
            certfile=config.certificate,
            keyfile=config.private_key,
        )

        context.load_verify_locations(
            cafile=config.ca_file,
        )

        return context

    @staticmethod
    def wrap_server(
        connection: socket.socket,
        context: ssl.SSLContext,
    ) -> ssl.SSLSocket:
        """
        Perform the TLS server handshake before returning the connection.
        """
        return context.wrap_socket(
            connection,
            server_side=True,
        )

    @staticmethod
    def wrap_client(
        connection: socket.socket,
        context: ssl.SSLContext,
        server_hostname: str,
    ) -> ssl.SSLSocket:
        """
        Perform the TLS client handshake before returning the connection.
        """
        return context.wrap_socket(
            connection,
            server_hostname=server_hostname,
        )

    @staticmethod
    def peer_certificate(
        connection: ssl.SSLSocket,
    ) -> dict:
        certificate = connection.getpeercert()

        if not certificate:
            raise ssl.SSLError("PEER CERTIFICATE NOT AVAILABLE")

        return certificate

    @staticmethod
    def send(connection, message: dict) -> None:
        payload = json.dumps(
            message,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

        if not payload:
            raise ValueError("INVALID EMPTY MESSAGE")

        if len(payload) > MAX_MESSAGE_SIZE:
            raise ValueError("MESSAGE TOO LARGE")

        connection.sendall(
            len(payload).to_bytes(4, "big")
            + payload
        )

    @staticmethod
    def receive(connection) -> dict:
        header = SecureTransport._read_exact(
            connection,
            4,
        )

        length = int.from_bytes(
            header,
            "big",
        )

        if length <= 0 or length > MAX_MESSAGE_SIZE:
            raise ValueError("INVALID MESSAGE LENGTH")

        payload = SecureTransport._read_exact(
            connection,
            length,
        )

        try:
            message = json.loads(
                payload.decode("utf-8")
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("INVALID JSON MESSAGE") from exc

        if not isinstance(message, dict):
            raise ValueError("INVALID MESSAGE TYPE")

        return message

    @staticmethod
    def _read_exact(connection, size: int) -> bytes:
        data = bytearray()

        while len(data) < size:
            chunk = connection.recv(
                size - len(data)
            )

            if not chunk:
                raise ConnectionError(
                    "CONNECTION CLOSED"
                )

            data.extend(chunk)

        return bytes(data)
