from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from core.state import State
from network.node import Node


class FakeConnection:
    def __init__(self, initiated_locally):
        self.initiated_locally = initiated_locally
        self._connected = True

    @property
    def connected(self):
        return self._connected

    def close(self):
        self._connected = False


def test_simultaneous_registration_keeps_preferred_connection():
    for _ in range(25):
        node = Node(
            "race-A",
            State({"alice": 10}),
            port=0,
        )
        peer_id = "race-B"

        incoming = FakeConnection(initiated_locally=False)
        outgoing = FakeConnection(initiated_locally=True)
        barrier = Barrier(3)

        def register(connection):
            barrier.wait(timeout=3)
            return node._register_peer_connection(peer_id, connection)

        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                incoming_future = pool.submit(register, incoming)
                outgoing_future = pool.submit(register, outgoing)

                barrier.wait(timeout=3)

                incoming_future.result(timeout=5)
                outgoing_future.result(timeout=5)

            assert node.peer_connections.get(peer_id) is outgoing
            assert outgoing.connected
            assert not incoming.connected

            # Una disconnessione tardiva non deve rimuovere
            # la connessione sostitutiva ancora valida.
            node._peer_disconnected(incoming)

            assert node.peer_connections.get(peer_id) is outgoing
            assert outgoing.connected
        finally:
            node.stop()


def test_stale_connection_cannot_remove_replacement():
    node = Node(
        "race-A",
        State({"alice": 10}),
        port=0,
    )
    peer_id = "race-B"

    old_connection = FakeConnection(initiated_locally=False)
    replacement = FakeConnection(initiated_locally=True)

    try:
        assert node._register_peer_connection(
            peer_id, old_connection
        )
        assert node._register_peer_connection(
            peer_id, replacement
        )

        assert not old_connection.connected
        assert node.peer_connections.get(peer_id) is replacement

        node._peer_disconnected(old_connection)

        assert node.peer_connections.get(peer_id) is replacement
        assert replacement.connected
    finally:
        node.stop()
