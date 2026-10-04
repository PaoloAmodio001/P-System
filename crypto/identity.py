from dataclasses import dataclass
from hashlib import sha256

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
