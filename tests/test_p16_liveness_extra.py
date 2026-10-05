from core.state import State
from network.node import Node
from network.peer import Peer


def test_p16_reconnect_success_resets_retry_state():
    node_a = Node("p16-extra-a", State({"alice": 10}), port=0)
    node_b = Node("p16-extra-b", State({"alice": 10}), port=0)

    try:
        node_a.start()
        node_b.start()

        node_a.add_peer(node_b)

        node_a._record_reconnect_failure(node_b.node_id)
        node_a._record_reconnect_failure(node_b.node_id)
        node_a._record_reconnect_failure(node_b.node_id)

        retry_state = node_a._reconnect_state[node_b.node_id]
        assert retry_state.attempts == 3
        assert retry_state.next_retry > 0

        node_a._record_reconnect_success(node_b.node_id)

        retry_state = node_a._reconnect_state[node_b.node_id]
        assert retry_state.attempts == 0
        assert retry_state.next_retry == 0.0
        assert retry_state.last_success is not None
    finally:
        node_a.stop()
        node_b.stop()
