import time

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


def wait_until(predicate, timeout=5.0, interval=0.01):
    """Poll ``predicate`` until it is true or ``timeout`` seconds elapse.

    Network tests must wait for a condition, not for a fixed time: message
    handling is asynchronous and its latency is not bounded by the test.
    Returns the final value of ``predicate()`` so callers can assert on it.
    """
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            return predicate()
        time.sleep(interval)
    return True
