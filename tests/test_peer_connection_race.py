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


def test_failed_connection_attempt_preserves_live_peer_state(monkeypatch):
    from types import SimpleNamespace

    node = Node(
        "race-A",
        State({"alice": 10}),
        port=0,
    )
    peer_id = "race-B"
    existing = FakeConnection(initiated_locally=False)
    node.peer_connections[peer_id] = existing

    class FailedConnection:
        def __init__(self, *args, **kwargs):
            pass

        def connect(self, peer, tls_config):
            raise ConnectionError("simulated concurrent connection failure")

        def close(self):
            pass

    monkeypatch.setattr("network.node.PeerConnection", FailedConnection)

    peer = SimpleNamespace(
        node_id=peer_id,
        host="127.0.0.1",
        port=12345,
    )

    try:
        assert node.open_peer_connection(peer) is False
        assert node.peer_connections[peer_id] is existing
        assert existing.connected

        state = node._reconnect_state[peer_id]
        assert state.attempts == 0
        assert state.next_retry > 0
    finally:
        node.stop()

def test_immediate_disconnect_during_thread_start_is_not_success(monkeypatch):
    from types import SimpleNamespace

    import network.node as node_module
    from network.peer import Peer

    node = Node("race-A", State({"alice": 10}), port=0)
    peer_id = "race-B"

    class DisconnectedConnection:
        def __init__(self, **kwargs):
            self.initiated_locally = True
            self.connected = True
            self.on_disconnect = None

        def connect(self, peer, tls_config):
            return SimpleNamespace(
                node_id=peer.node_id,
                host=peer.host,
                port=peer.port,
            )

        def close(self):
            self.connected = False

        def receive_loop(self, handler):
            pass

    class ImmediateDisconnectThread:
        def __init__(self, target, args=(), kwargs=None, daemon=None):
            pass

        def start(self):
            connection = node.peer_connections[peer_id]
            connection.connected = False
            connection.on_disconnect(connection)

    peer = Peer(peer_id, "127.0.0.1", 12345)
    node.add_peer(peer)

    try:
        monkeypatch.setattr(
            node_module, "PeerConnection", DisconnectedConnection
        )
        monkeypatch.setattr(
            node_module.threading, "Thread", ImmediateDisconnectThread
        )

        assert node.open_peer_connection(peer) is False
        assert peer_id not in node.peer_connections

        state = node._reconnect_state[peer_id]
        assert state.attempts >= 1
        assert state.next_retry > 0
    finally:
        node.stop()
