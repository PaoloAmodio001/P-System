from core.decision_status import DecisionStatus
from core.event import Transfer
from core.state import State
from network.node import Node


def test_node_with_missing_parent_is_not_unique():
    parent = Transfer(
        "alice",
        "bob",
        5,
        0,
    )

    child = Transfer(
        "bob",
        "carol",
        2,
        0,
        parents=(parent.event_id(),),
    )

    node = Node(
        "node-A",
        State({"bob": 2}),
    )

    # The node knows the child but not its declared parent.
    node.events.append(child)

    # A node with an explicitly incomplete causal history
    # must not claim a unique decision.
    assert node.status() == DecisionStatus.UNCERTAIN


def test_node_with_complete_known_history_can_remain_unique():
    parent = Transfer(
        "alice",
        "bob",
        5,
        0,
    )

    child = Transfer(
        "bob",
        "carol",
        2,
        0,
        parents=(parent.event_id(),),
    )

    node = Node(
        "node-A",
        State({"alice": 5}),
    )

    node.events.append(parent)
    node.events.append(child)

    assert node.status() == DecisionStatus.UNIQUE
