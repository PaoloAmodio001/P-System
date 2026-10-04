import time

from core.event import Transfer
from core.state import State
from network.node import Node


def test_node_syncs_events_over_tcp():
    node_a = Node(
        "node-A",
        State({"alice": 10}),
        port=0,
    )

    node_b = Node(
        "node-B",
        State({"alice": 10}),
        port=0,
    )

    node_a.start()
    node_b.start()

    try:
        tx = Transfer(
            "alice",
            "bob",
            4,
            0,
        )

        assert node_a.receive(tx)

        node_a.sync_with(node_b)

        deadline = time.time() + 2

        while (
            tx not in node_b.events
            and time.time() < deadline
        ):
            time.sleep(0.01)

        assert tx in node_b.events

        assert node_b.state.balance("alice") == 6
        assert node_b.state.balance("bob") == 4
        assert node_b.state.nonce("alice") == 1

    finally:
        node_a.stop()
        node_b.stop()
