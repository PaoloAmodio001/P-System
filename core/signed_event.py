from dataclasses import dataclass
from hashlib import sha256

from core.event import Transfer
from crypto.identity import Identity, verify_signature


@dataclass(frozen=True)
class SignedTransfer:
    transfer: Transfer
    public_key: bytes
    signature: bytes

    @classmethod
    def create(
        cls,
        identity: Identity,
        transfer: Transfer,
    ):
        return cls(
            transfer=transfer,
            public_key=identity.public_key,
            signature=identity.sign(
                transfer.canonical()
            ),
        )

    def verify(self) -> bool:
        return verify_signature(
            self.public_key,
            self.signature,
            self.transfer.canonical(),
        )

    def identity_binding(self) -> str:
        """
        Deterministic cryptographic identifier derived from
        the public key.
        """
        return sha256(
            self.public_key
        ).hexdigest()

    @property
    def identity_id(self) -> str:
        """
        Cryptographic identity of the signer.
        """
        return self.identity_binding()

    def verify_identity_binding(
        self,
        identity_id: str,
    ) -> bool:
        """
        Verify that this signed event was produced by
        the cryptographic identity identified by identity_id.
        """
        return (
            self.verify()
            and self.identity_id == identity_id
        )
