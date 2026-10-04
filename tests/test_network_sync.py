from core.event import Transfer
from core.state import State
from network.node import Node
from network.sync import decode_events, encode_events


def test_event_sync_roundtrip():
    node = Node(
        "node-A",
        State({"alice": 10}),
    )

    tx_a = Transfer(
        "alice",
        "bob",
        8,
        0,
    )

    tx_b = Transfer(
        "alice",
        "carol",
        8,
        0,
    )

    assert node.receive(tx_a)
    assert node.receive(tx_b) is False

    message = encode_events(node)

    restored = decode_events(message)

    assert restored == [tx_a]
    assert message["type"] == "EVENT_SYNC"
