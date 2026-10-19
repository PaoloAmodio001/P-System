from core.event import Transfer
from core.state import State
from network.node import Node


def test_rebuild_preserves_previously_executed_event_after_conflict():
    node = Node(
        node_id="conflict-rebuild-regression",
        initial_state=State({"alice": 10}),
        port=0,
    )

    try:
        executed = Transfer("alice", "bob", 1, 0)
        alternative = Transfer("alice", "carol", 1, 0)

        assert node.receive(executed, broadcast=False)
        assert not node.receive(alternative, broadcast=False)

        # Rebuilding must not silently undo a previously executed event.
        node._rebuild_local_projection()

        assert node.state.balance("alice") == 9
        assert node.state.balance("bob") == 1
        assert node.state.balance("carol") == 0
        assert executed in node.local_events
        assert alternative not in node.local_events
    finally:
        node.stop()

def test_rebuild_preserves_executed_causal_child_after_conflict():
    node = Node(
        node_id="conflict-rebuild-child",
        initial_state=State({"alice": 10}),
        port=0,
    )

    try:
        executed = Transfer("alice", "bob", 1, 0)
        child = Transfer(
            "bob", "dave", 1, 0,
            parents=(executed.event_id(),),
        )
        alternative = Transfer("alice", "carol", 1, 0)

        assert node.receive(executed, broadcast=False)
        assert node.receive(child, broadcast=False)
        assert not node.receive(alternative, broadcast=False)

        node._rebuild_local_projection()
        node._rebuild_local_projection()

        assert node.state.balance("alice") == 9
        assert node.state.balance("bob") == 0
        assert node.state.balance("dave") == 1
        assert node.state.balance("carol") == 0
        assert executed in node.local_events
        assert child in node.local_events
        assert alternative not in node.local_events
    finally:
        node.stop()
