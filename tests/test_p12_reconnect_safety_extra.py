from core.state import State
from network.node import Node
from network.reconciliation import reconcile
from tests.signed_helpers import identity_with_claim, signed_transfer


def test_p12_reconciliation_is_idempotent():
    identity, claim = identity_with_claim("alice")
    transfer, signed = signed_transfer(identity, "alice", "bob", 4, 0)

    node_a = Node("p12-extra-a", State({"alice": 4}), port=0)
    node_b = Node("p12-extra-b", State({"alice": 4}), port=0)

    try:
        assert node_a.register_identity_claim(claim)
        assert node_b.register_identity_claim(claim)

        assert node_a.receive_signed(signed, broadcast=False)

        reconcile(node_a, node_b)
        first_state = node_b.state.copy()
        first_events = tuple(node_b.events)
        first_local = tuple(node_b.local_events)

        reconcile(node_a, node_b)
        reconcile(node_a, node_b)

        assert tuple(node_b.events) == first_events
        assert tuple(node_b.local_events) == first_local
        assert node_b.state.root() == first_state.root()
        assert node_b.state.balance("bob") == 4
        assert node_b.state.nonce("alice") == 1
        assert node_b.events.count(transfer) == 1
    finally:
        node_a.stop()
        node_b.stop()
