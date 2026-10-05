
from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from network.secure_transport import TLSConfig


_lock = Lock()
_state = None


def _save_key(path: Path, key) -> None:
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )


def _create_ca(directory: Path):
    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    subject = x509.Name([
        x509.NameAttribute(
            NameOID.COMMON_NAME,
            "P-System P14 Local CA",
        )
    ])

    now = datetime.now(timezone.utc)

    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
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
        .sign(
            key,
            hashes.SHA256(),
        )
    )

    key_path = directory / "ca.key"
    cert_path = directory / "ca.crt"

    _save_key(key_path, key)
    cert_path.write_bytes(
        certificate.public_bytes(
            serialization.Encoding.PEM
        )
    )

    return key, cert_path


def _create_node_certificate(
    directory: Path,
    node_id: str,
    ca_key,
    ca_cert_path: Path,
) -> TLSConfig:

    ca_certificate = x509.load_pem_x509_certificate(
        ca_cert_path.read_bytes()
    )

    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    subject = x509.Name([
        x509.NameAttribute(
            NameOID.COMMON_NAME,
            node_id,
        )
    ])

    now = datetime.now(timezone.utc)

    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_certificate.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName(node_id),
            ]),
            critical=False,
        )
        .sign(
            ca_key,
            hashes.SHA256(),
        )
    )

    safe_id = "".join(
        c if c.isalnum() or c in "._-" else "_"
        for c in node_id
    )

    key_path = directory / f"{safe_id}.key"
    cert_path = directory / f"{safe_id}.crt"

    _save_key(key_path, key)

    cert_path.write_bytes(
        certificate.public_bytes(
            serialization.Encoding.PEM
        )
    )

    return TLSConfig(
        certificate=str(cert_path),
        private_key=str(key_path),
        ca_file=str(ca_cert_path),
        server_hostname=node_id,
    )


def get_node_tls_config(node_id: str) -> TLSConfig:
    global _state

    with _lock:
        if _state is None:
            directory = Path(
                tempfile.mkdtemp(
                    prefix="psystem-p14-"
                )
            )

            ca_key, ca_cert = _create_ca(
                directory
            )

            _state = {
                "directory": directory,
                "ca_key": ca_key,
                "ca_cert": ca_cert,
                "nodes": {},
            }

        if node_id not in _state["nodes"]:
            _state["nodes"][node_id] = (
                _create_node_certificate(
                    _state["directory"],
                    node_id,
                    _state["ca_key"],
                    _state["ca_cert"],
                )
            )

        return _state["nodes"][node_id]
