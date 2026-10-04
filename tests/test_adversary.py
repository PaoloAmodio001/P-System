from core.event import Transfer
from core.signed_event import SignedTransfer
from crypto.identity import Identity
from simulator.adversary import AdversarialNetwork


def test_malicious_nodes_cannot_forge_event():

    network = AdversarialNetwork(
        node_count=10,
        malicious={"node-6", "node-7"},
    )

    alice = Identity.create()

    tx = Transfer(
        "alice",
        "bob",
        5,
        0,
    )

    signed = SignedTransfer.create(
        alice,
        tx,
    )

    honest_observers = {
        "node-1",
        "node-2",
        "node-3",
        "node-4",
        "node-5",
        "node-8",
        "node-9",
        "node-10",
    }

    evidence = network.observe(
        signed,
        honest_observers,
    )

    assert evidence.valid()

    assert evidence.strength() == 8


def test_malicious_nodes_cannot_modify_signed_event():

    network = AdversarialNetwork(
        node_count=10,
        malicious={"node-6", "node-7"},
    )

    alice = Identity.create()

    original = Transfer(
        "alice",
        "bob",
        5,
        0,
    )

    signed = SignedTransfer.create(
        alice,
        original,
    )

    malicious_version = Transfer(
        "alice",
        "node-6",
        500,
        0,
    )

    forged = SignedTransfer(
        malicious_version,
        signed.public_key,
        signed.signature,
    )

    evidence = network.observe(
        forged,
        {
            "node-6",
            "node-7",
        },
    )

    assert not evidence.valid()
