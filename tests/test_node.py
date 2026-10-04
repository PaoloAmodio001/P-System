import time

from core.event import Transfer
from core.signed_event import SignedTransfer
from core.state import State
from crypto.identity import Identity
from network.node import Node


def test_node_receives_and_verifies_signed_transfer():
    sender_identity = Identity.create()

    sender_node = Node(
        node_id="node-A",
        initial_state=State({"alice": 10}),
        port=0,
    )

    receiver_node = Node(
        node_id="node-B",
        initial_state=State({"alice": 10}),
        port=0,
    )

    sender_node.start()
    receiver_node.start()

    try:
        transfer = Transfer(
            sender="alice",
            receiver="bob",
            amount=5,
            nonce=0,
        )

        signed = SignedTransfer.create(
            sender_identity,
            transfer,
        )

        assert sender_node.send_signed_transfer(
            receiver_node,
            signed,
        )

        deadline = time.time() + 2

        while (
            not receiver_node.received
            and time.time() < deadline
        ):
            time.sleep(0.01)

        assert len(receiver_node.received) == 1

        received = receiver_node.received[0]

        assert received.transfer == transfer
        assert received.public_key == signed.public_key
        assert received.signature == signed.signature
        assert received.verify()

    finally:
        sender_node.stop()
        receiver_node.stop()
