import time

from core.state import State
from network.node import Node
from network.peer import Peer


def test_p16_reconnect_eventually_restores_peer_connection():
    node_a = Node(
        "p16-node-A",
        State({"alice": 10}),
        port=0,
    )

    node_b = Node(
        "p16-node-B",
        State({"alice": 10}),
        port=0,
    )

    try:
        node_a.start()
        node_b.start()

        node_a.add_peer(node_b)

        assert node_a.connect_peer(node_b)

        connection = node_a.peer_connections.get(node_b.node_id)
        assert connection is not None
        assert connection.connected

        old_port = node_b.port

        node_b.stop()

        disconnected_deadline = time.monotonic() + 3.0

        while (
            node_b.node_id in node_a.peer_connections
            and time.monotonic() < disconnected_deadline
        ):
            time.sleep(0.01)

        assert node_b.node_id not in node_a.peer_connections

        node_b = Node(
            "p16-node-B",
            State({"alice": 10}),
            port=0,
        )
        node_b.start()

        assert node_b.port != old_port

        node_a.peers[node_b.node_id] = Peer(
            node_id=node_b.node_id,
            host=node_b.host,
            port=node_b.port,
        )

        reconnect_deadline = time.monotonic() + 8.0

        while time.monotonic() < reconnect_deadline:
            connection = node_a.peer_connections.get(
                node_b.node_id
            )

            if (
                connection is not None
                and connection.connected
            ):
                break

            time.sleep(0.05)

        connection = node_a.peer_connections.get(
            node_b.node_id
        )

        assert connection is not None
        assert connection.connected

        state = node_a._reconnect_state[node_b.node_id]

        assert state.last_success is not None
        assert state.attempts == 0

    finally:
        node_a.stop()
        node_b.stop()
