import time

from core.event import Transfer
from core.signed_event import SignedTransfer
from core.state import State
from crypto.identity import Identity
from network.message import encode_signed_transfer
from network.node import Node
from network.transport import TCPTransport


def test_node_to_node_signed_transfer():
    sender_identity = Identity.create()

    node_a = Node(
        node_id="node-A",
        initial_state=State({"alice": 10}),
        port=0,
    )

    node_b = Node(
        node_id="node-B",
        initial_state=State({"alice": 10}),
        port=0,
    )

    node_a.start()
    node_b.start()

    try:
        transfer = Transfer(
            sender="alice",
            receiver="bob",
            amount=4,
            nonce=0,
        )

        signed = SignedTransfer.create(
            sender_identity,
            transfer,
        )

        assert node_a.send_signed_transfer(
            node_b,
            signed,
        )

        deadline = time.time() + 2

        while (
            not node_b.received
            and time.time() < deadline
        ):
            time.sleep(0.01)

        assert len(node_b.received) == 1

        assert node_b.received[0].verify()

        assert node_b.state.balance("alice") == 6
        assert node_b.state.balance("bob") == 4
        assert node_b.state.nonce("alice") == 1

    finally:
        node_a.stop()
        node_b.stop()
