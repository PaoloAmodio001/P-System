import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from core.state import State
from tests.node_helpers import standalone_node


def test_real_tls_simultaneous_connections_keep_one_connection():
    node_a = standalone_node("race-real-A", State({"alice": 10}), port=0)
    node_b = standalone_node("race-real-B", State({"alice": 10}), port=0)
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

        assert result_a, "node A did not complete the connection"
        assert result_b, "node B did not complete the connection"

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
        assert conn_a.initiated_locally, "A must keep its outgoing connection"
        assert not conn_b.initiated_locally, "B must keep its incoming connection"

        # Traffic on the connections kept: a request for certificates each way.
        node_a._request_certificates(conn_a)
        node_b._request_certificates(conn_b)
        time.sleep(0.2)

        # The traffic must not have replaced the connection kept.
        assert node_a.peer_connections.get(node_b.node_id) is conn_a
        assert node_b.peer_connections.get(node_a.node_id) is conn_b
        assert conn_a.connected and conn_b.connected

    finally:
        for node in nodes:
            node.stop()
