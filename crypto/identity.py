import os
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


@dataclass
class Identity:
    private_key: Ed25519PrivateKey

    @classmethod
    def create(cls):
        return cls(
            Ed25519PrivateKey.generate()
        )

    @property
    def public_key(self) -> bytes:
        return self.private_key.public_key().public_bytes_raw()

    @property
    def identity_id(self) -> str:
        """
        Deterministic identifier derived from the public key.

        The identity_id is the cryptographic identity of the account.
        Human-readable names remain aliases and are not security roots.
        """
        return sha256(
            self.public_key
        ).hexdigest()

    def sign(self, data: bytes) -> bytes:
        return self.private_key.sign(data)

    def save(self, path: Path) -> None:
        """Write the private key, readable only by its owner. Never over an existing file."""
        data = self.private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)

        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())

    @classmethod
    def load(cls, path: Path) -> "Identity":
        """Read a key saved by `save`. A key that others can read is refused."""
        path = Path(path)

        if path.stat().st_mode & 0o077:
            raise ValueError(f"KEY FILE IS READABLE BY OTHERS: {path}")

        key = serialization.load_pem_private_key(path.read_bytes(), None)

        if not isinstance(key, Ed25519PrivateKey):
            raise ValueError(f"NOT AN ED25519 KEY: {path}")

        return cls(key)


def verify_signature(
    public_key: bytes,
    signature: bytes,
    data: bytes,
) -> bool:

    try:
        key = Ed25519PublicKey.from_public_bytes(
            public_key
        )

        key.verify(
            signature,
            data,
        )

        return True

    except Exception:
        return False
