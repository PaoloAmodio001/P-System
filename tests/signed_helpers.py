from core.event import Transfer
from core.identity_claim import IdentityClaim
from core.signed_event import SignedTransfer
from crypto.identity import Identity


def identity_with_claim(alias: str):
    identity = Identity.create()
    claim = IdentityClaim.create(identity, alias)
    return identity, claim


def signed_transfer(identity, sender, receiver, amount, nonce, parents=()):
    transfer = Transfer(
        sender=sender,
        receiver=receiver,
        amount=amount,
        nonce=nonce,
        parents=tuple(parents),
    )
    return transfer, SignedTransfer.create(identity, transfer)


def authorize(node, claim):
    assert node.register_identity_claim(claim)
