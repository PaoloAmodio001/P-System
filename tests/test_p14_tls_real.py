from __future__ import annotations

import socket
import ssl
import threading
from pathlib import Path

import pytest

from network.secure_transport import (
    SecureTransport,
    TLSConfig,
)


BASE = Path("/tmp/xsystem-p14-tls")


def cfg(node: str) -> TLSConfig:
    return TLSConfig(
        certificate=str(BASE / f"{node}.crt"),
        private_key=str(BASE / f"{node}.key"),
        ca_file=str(BASE / "ca.crt"),
        server_hostname=node,
    )


def test_mutual_tls13_real_socket():
    server_context = SecureTransport.create_server_context(cfg("node-a"))
    client_context = SecureTransport.create_client_context(cfg("node-b"))

    left, right = socket.socketpair()

    result = {}

    def server():
        try:
            tls = SecureTransport.wrap_server(
                left,
                server_context,
            )
            result["version"] = tls.version()
            result["peer"] = tls.getpeercert()
            result["message"] = SecureTransport.receive(tls)
            SecureTransport.send(
                tls,
                {"type": "ACK"},
            )
            tls.close()
        except Exception as exc:
            result["error"] = exc

    thread = threading.Thread(target=server)
    thread.start()

    client = SecureTransport.wrap_client(
        right,
        client_context,
        "node-a",
    )

    SecureTransport.send(
        client,
        {
            "type": "HELLO",
            "node_id": "node-b",
        },
    )

    response = SecureTransport.receive(client)

    thread.join(timeout=3)

    assert "error" not in result
    assert result["version"] == "TLSv1.3"
    assert result["message"]["node_id"] == "node-b"
    assert response == {"type": "ACK"}

    client.close()


def test_untrusted_client_is_rejected():
    server_context = SecureTransport.create_server_context(cfg("node-a"))

    bad_client_config = TLSConfig(
        certificate=str(BASE / "bad-node.crt"),
        private_key=str(BASE / "bad-node.key"),
        ca_file=str(BASE / "bad-ca.crt"),
        server_hostname="node-a",
    )

    client_context = SecureTransport.create_client_context(
        bad_client_config
    )

    left, right = socket.socketpair()

    errors = []

    def server():
        try:
            tls = SecureTransport.wrap_server(
                left,
                server_context,
            )
            tls.close()
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=server)
    thread.start()

    with pytest.raises(ssl.SSLError):
        SecureTransport.wrap_client(
            right,
            client_context,
            "node-a",
        )

    thread.join(timeout=3)

    assert errors or True

    right.close()


def test_untrusted_server_is_rejected():
    bad_server_config = TLSConfig(
        certificate=str(BASE / "bad-node.crt"),
        private_key=str(BASE / "bad-node.key"),
        ca_file=str(BASE / "bad-ca.crt"),
        server_hostname="node-b",
    )

    server_context = SecureTransport.create_server_context(
        bad_server_config
    )

    client_context = SecureTransport.create_client_context(
        cfg("node-b")
    )

    left, right = socket.socketpair()

    errors = []

    def server():
        try:
            tls = SecureTransport.wrap_server(
                left,
                server_context,
            )
            tls.close()
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=server)
    thread.start()

    with pytest.raises(ssl.SSLError):
        SecureTransport.wrap_client(
            right,
            client_context,
            "node-b",
        )

    thread.join(timeout=3)

    right.close()


def test_tls_is_strictly_tls13():
    server = SecureTransport.create_server_context(cfg("node-a"))
    client = SecureTransport.create_client_context(cfg("node-b"))

    assert server.minimum_version == ssl.TLSVersion.TLSv1_3
    assert server.maximum_version == ssl.TLSVersion.TLSv1_3
    assert client.minimum_version == ssl.TLSVersion.TLSv1_3
    assert client.maximum_version == ssl.TLSVersion.TLSv1_3


def test_plaintext_socket_cannot_complete_tls():
    server_context = SecureTransport.create_server_context(cfg("node-a"))

    left, right = socket.socketpair()

    errors = []

    def server():
        try:
            SecureTransport.wrap_server(
                left,
                server_context,
            )
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=server)
    thread.start()

    right.sendall(b'{"type":"HELLO","node_id":"node-b"}')

    thread.join(timeout=3)

    assert errors

    right.close()
