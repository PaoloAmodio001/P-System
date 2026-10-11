import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from core.state import State
from network.node import Node
from tests.signed_helpers import authorize, identity_with_claim, signed_transfer


def test_real_tls_simultaneous_connections_and_signed_sync():
    node_a = Node("race-real-A", State({"alice": 10}), port=0)
    node_b = Node("race-real-B", State({"alice": 10}), port=0)
    nodes = (node_a, node_b)

    try:
        node_a.start()
        node_b.start()

        node_a.add_peer(node_b)
        node_b.add_peer(node_a)

        barrier = Barrier(3)

        def connect(node, peer):
            barrier.wait(timeout=5)
            return node.connect_peer(peer)

        with ThreadPoolExecutor(max_workers=2) as pool:
            future_a = pool.submit(connect, node_a, node_b)
            future_b = pool.submit(connect, node_b, node_a)

            barrier.wait(timeout=5)
            result_a = future_a.result(timeout=10)
            result_b = future_b.result(timeout=10)

        assert result_a, "Il nodo A non ha completato la connessione"
        assert result_b, "Il nodo B non ha completato la connessione"

        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            conn_a = node_a.peer_connections.get(node_b.node_id)
            conn_b = node_b.peer_connections.get(node_a.node_id)

            if (
                conn_a is not None
                and conn_b is not None
                and conn_a.connected
                and conn_b.connected
                and conn_a.initiated_locally
                and not conn_b.initiated_locally
            ):
                break
            time.sleep(0.02)

        conn_a = node_a.peer_connections.get(node_b.node_id)
        conn_b = node_b.peer_connections.get(node_a.node_id)

        assert conn_a is not None and conn_a.connected
        assert conn_b is not None and conn_b.connected
        assert conn_a.initiated_locally, "A deve mantenere la connessione uscente"
        assert not conn_b.initiated_locally, "B deve mantenere la connessione entrante"

        identity, claim = identity_with_claim("alice")
        for node in nodes:
            authorize(node, claim)

        tx, signed = signed_transfer(identity, "alice", "bob", 1, 0)
        assert node_a.receive_signed(signed, broadcast=False)

        node_a.sync_with(node_b)

        deadline = time.monotonic() + 5
        while tx not in node_b.events and time.monotonic() < deadline:
            time.sleep(0.02)

        assert tx in node_b.events, "Il trasferimento firmato non è arrivato a B"

        # La sincronizzazione non deve aver sostituito la connessione corretta.
        assert node_a.peer_connections.get(node_b.node_id) is conn_a
        assert node_b.peer_connections.get(node_a.node_id) is conn_b
        assert conn_a.connected and conn_b.connected

    finally:
        for node in nodes:
            node.stop()
