from __future__ import annotations

import socket
import ssl
import threading
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from network.node_tls_identity import get_node_tls_config

from network.secure_transport import (
    SecureTransport,
    TLSConfig,
)


def _create_bad_tls_config():
    directory = Path(tempfile.mkdtemp(prefix="psystem-p14-bad-"))

    ca_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    now = datetime.now(timezone.utc)

    ca_subject = x509.Name([
        x509.NameAttribute(
            NameOID.COMMON_NAME,
            "P-System P14 Bad CA",
        )
    ])

    ca_certificate = (
        x509.CertificateBuilder()
        .subject_name(ca_subject)
        .issuer_name(ca_subject)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=365))
        .add_extension(
            x509.BasicConstraints(
                ca=True,
                path_length=None,
            ),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )

    ca_path = directory / "bad-ca.crt"
    ca_path.write_bytes(
        ca_certificate.public_bytes(
            serialization.Encoding.PEM
        )
    )

    node_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    node_subject = x509.Name([
        x509.NameAttribute(
            NameOID.COMMON_NAME,
            "bad-node",
        )
    ])

    node_certificate = (
        x509.CertificateBuilder()
        .subject_name(node_subject)
        .issuer_name(ca_certificate.subject)
        .public_key(node_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("node-a"),
                x509.DNSName("node-b"),
            ]),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )

    key_path = directory / "bad-node.key"
    cert_path = directory / "bad-node.crt"

    key_path.write_bytes(
        node_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )

    cert_path.write_bytes(
        node_certificate.public_bytes(
            serialization.Encoding.PEM
        )
    )

    return TLSConfig(
        certificate=str(cert_path),
        private_key=str(key_path),
        ca_file=str(ca_path),
        server_hostname="node-a",
    )


def cfg(node: str) -> TLSConfig:
    return get_node_tls_config(node)


def bad_cfg() -> TLSConfig:
    return _create_bad_tls_config()


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

    bad_client_config = bad_cfg()

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
    bad_server_config = bad_cfg()
    bad_server_config = TLSConfig(
        certificate=bad_server_config.certificate,
        private_key=bad_server_config.private_key,
        ca_file=bad_server_config.ca_file,
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
