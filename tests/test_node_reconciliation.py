from core.conflict_state import ConflictState
from core.event import Transfer
from core.state import State
from network.node import Node
from network.reconciliation import reconcile


def test_reconnect_preserves_both_conflicting_events():
    node_a = Node(
        "node-A",
        State({"alice": 10}),
    )

    node_b = Node(
        "node-B",
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

    assert node_a.receive(tx_a)
    assert node_b.receive(tx_b)

    root_a_before = node_a.state_root()
    root_b_before = node_b.state_root()

    assert root_a_before != root_b_before

    reconcile(node_a, node_b)

    assert set(node_a.events) == {
        tx_a,
        tx_b,
    }

    assert set(node_b.events) == {
        tx_a,
        tx_b,
    }

    conflict = ConflictState(
        tuple(sorted(
            [tx_a, tx_b],
            key=lambda event: event.event_id(),
        ))
    )

    assert conflict.is_conflicted()
    assert not conflict.has_winner()
