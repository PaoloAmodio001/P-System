import time

from core.conflict_state import ConflictState
from core.event import Transfer
from core.state import State
from network.conflicted_state import ConflictedState
from network.node import Node


def test_conflicting_events_sync_over_tcp_without_winner():
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

        # Partition: each node accepts a different event.
        assert node_a.receive(tx_a)
        assert node_b.receive(tx_b)

        assert node_a.state_root() != node_b.state_root()

        # Reconnect: exchange knowledge through real TCP.
        node_a.sync_with(node_b)
        node_b.sync_with(node_a)

        deadline = time.time() + 2

        while (
            (
                tx_a not in node_a.events
                or tx_b not in node_a.events
                or tx_a not in node_b.events
                or tx_b not in node_b.events
            )
            and time.time() < deadline
        ):
            time.sleep(0.01)

        assert set(node_a.events) == {
            tx_a,
            tx_b,
        }

        assert set(node_b.events) == {
            tx_a,
            tx_b,
        }

        # The states remain different: knowledge converged,
        # but no conflicting event was automatically executed.
        assert node_a.state_root() != node_b.state_root()

        conflict = ConflictState(
            tuple(sorted(
                [tx_a, tx_b],
                key=lambda event: event.event_id(),
            ))
        )

        conflicted_a = ConflictedState(
            base_state=node_a.state,
            alternatives=conflict,
        )

        conflicted_b = ConflictedState(
            base_state=node_b.state,
            alternatives=conflict,
        )

        assert conflicted_a.is_conflicted
        assert conflicted_b.is_conflicted

        assert not conflicted_a.has_winner
        assert not conflicted_b.has_winner

    finally:
        node_a.stop()
        node_b.stop()
