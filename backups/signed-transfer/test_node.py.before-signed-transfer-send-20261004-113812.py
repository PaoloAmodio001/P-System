import time

from core.event import Transfer
from core.signed_event import SignedTransfer
from core.state import State
from crypto.identity import Identity
from network.node import Node
from network.message import encode_signed_transfer
from network.transport import TCPTransport


def test_node_receives_and_verifies_signed_transfer():
    sender = Identity.create()

    node = Node(
        node_id="node-B",
        initial_state=State({"alice": 10}),
        port=0,
    )

    node.start()

    try:
        transfer = Transfer(
            sender="alice",
            receiver="bob",
            amount=5,
            nonce=0,
        )

        signed = SignedTransfer.create(
            sender,
            transfer,
        )

        class LocalPeer:
            def address(self):
                return node.address()

        transport = TCPTransport(
            "127.0.0.1",
            0,
        )

        transport.send(
            LocalPeer(),
            encode_signed_transfer(signed),
        )

        deadline = time.time() + 2

        while (
            not node.received
            and time.time() < deadline
        ):
            time.sleep(0.01)

        assert len(node.received) == 1

        received = node.received[0]

        assert received.transfer == transfer
        assert received.public_key == signed.public_key
        assert received.signature == signed.signature
        assert received.verify()

    finally:
        node.stop()
