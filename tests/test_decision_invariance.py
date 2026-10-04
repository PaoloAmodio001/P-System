from core.decision_status import DecisionStatus
from core.event import Transfer
from core.state import State
from network.node import Node


def test_decision_is_not_invariant_if_relevant_extension_changes_status():
    visible = Transfer(
        "alice",
        "bob",
        5,
        0,
    )

    hidden = Transfer(
        "alice",
        "carol",
        5,
        0,
    )

    node = Node(
        "node-A",
        State({"alice": 10}),
    )

    assert node.receive(visible)

    initial_status = node.status()

    assert initial_status == DecisionStatus.UNIQUE

    # Extension of the knowledge with a previously unknown
    # concurrent event.
    node.events.append(hidden)

    extended_status = node.status()

    assert extended_status == DecisionStatus.CONFLICTED
    assert extended_status != initial_status


def test_decision_can_remain_invariant_under_irrelevant_extension():
    visible = Transfer(
        "alice",
        "bob",
        5,
        0,
    )

    unrelated = Transfer(
        "carol",
        "dave",
        3,
        0,
    )

    node = Node(
        "node-A",
        State({
            "alice": 10,
            "carol": 10,
        }),
    )

    assert node.receive(visible)

    initial_status = node.status()

    assert initial_status == DecisionStatus.UNIQUE

    node.events.append(unrelated)

    extended_status = node.status()

    assert extended_status == DecisionStatus.UNIQUE
    assert extended_status == initial_status
