from dataclasses import dataclass
from hashlib import sha256

from crypto.identity import Identity, verify_signature


@dataclass(frozen=True)
class IdentityClaim:
    identity_id: str
    alias: str
    public_key: bytes
    signature: bytes

    @classmethod
    def create(
        cls,
        identity: Identity,
        alias: str,
    ) -> "IdentityClaim":
        identity_id = sha256(
            identity.public_key
        ).hexdigest()

        payload = (
            identity_id.encode()
            + b":"
            + alias.encode()
            + b":"
            + identity.public_key
        )

        return cls(
            identity_id=identity_id,
            alias=alias,
            public_key=identity.public_key,
            signature=identity.sign(payload),
        )

    def verify(self) -> bool:
        expected_identity_id = sha256(
            self.public_key
        ).hexdigest()

        if self.identity_id != expected_identity_id:
            return False

        payload = (
            self.identity_id.encode()
            + b":"
            + self.alias.encode()
            + b":"
            + self.public_key
        )

        return verify_signature(
            self.public_key,
            self.signature,
            payload,
        )

    def identity_binding(self) -> str:
        return self.identity_id
