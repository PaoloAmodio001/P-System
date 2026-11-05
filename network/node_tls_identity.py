"""
TLS identities of nodes: an authority, and a certificate for each node id.

`create_authority` and `issue_node_certificate` are for real deployments, usually through the
`psystem` command. All the nodes of a deployment trust one authority, and a certificate names one
node id. The authority decides who may connect, not who may vote: votes are signed with the keys
of the committee, and a stolen certificate gives no vote.

`get_node_tls_config` gives a throwaway authority, private to the process, for tests and
experiments. Two processes that use it cannot connect to each other, on purpose.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from network.secure_transport import TLSConfig

_lock = Lock()
_state = None

AUTHORITY_DAYS = 3650
NODE_DAYS = 365


@dataclass(frozen=True)
class Authority:
    directory: Path
    key: ec.EllipticCurvePrivateKey
    certificate_path: Path


def _write_private(path: Path, data: bytes) -> None:
    # Created with these permissions, so that the key is never readable by others, even for
    # a moment. An existing key is an error: overwriting one is never what was meant.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)


def _key_bytes(key) -> bytes:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def _new_key():
    return ec.generate_private_key(ec.SECP256R1())


def create_authority(directory: Path, days: int = AUTHORITY_DAYS) -> Authority:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = _new_key()
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "P-System authority")])
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=days))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(key, hashes.SHA256())
    )
    _write_private(directory / "ca.key", _key_bytes(key))
    certificate_path = directory / "ca.crt"
    certificate_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    return Authority(directory, key, certificate_path)


def load_authority(directory: Path) -> Authority:
    directory = Path(directory)
    key = serialization.load_pem_private_key((directory / "ca.key").read_bytes(), None)
    return Authority(directory, key, directory / "ca.crt")


def issue_node_certificate(
    authority: Authority,
    node_id: str,
    directory: Path,
    days: int = NODE_DAYS,
) -> TLSConfig:
    """A key and a certificate for `node_id`, in `directory`, with the path of the authority."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    ca_certificate = x509.load_pem_x509_certificate(authority.certificate_path.read_bytes())
    key = _new_key()
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, node_id)]))
        .issuer_name(ca_certificate.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=days))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(node_id)]), critical=False)
        .sign(authority.key, hashes.SHA256())
    )
    safe_id = "".join(c if c.isalnum() or c in "._-" else "_" for c in node_id)
    key_path = directory / f"{safe_id}.key"
    certificate_path = directory / f"{safe_id}.crt"
    _write_private(key_path, _key_bytes(key))
    certificate_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    return TLSConfig(
        certificate=str(certificate_path),
        private_key=str(key_path),
        ca_file=str(authority.certificate_path),
        server_hostname=node_id,
    )


def get_node_tls_config(node_id: str) -> TLSConfig:
    """A certificate of a throwaway authority of this process: see the top of this file."""
    global _state

    with _lock:
        if _state is None:
            directory = Path(tempfile.mkdtemp(prefix="psystem-p14-"))
            _state = {
                "directory": directory,
                "authority": create_authority(directory),
                "nodes": {},
            }

        if node_id not in _state["nodes"]:
            _state["nodes"][node_id] = issue_node_certificate(
                _state["authority"],
                node_id,
                _state["directory"],
            )

        return _state["nodes"][node_id]
