from core.decision_status import DecisionStatus
from core.event import Transfer
from core.relevance_graph import RelevanceGraph
from network.node import Node


def test_runtime_hidden_relevant_event_prevents_unique_decision():
    visible = Transfer(
        sender="alice",
        receiver="bob",
        amount=3,
        nonce=0,
    )

    hidden = Transfer(
        sender="alice",
        receiver="carol",
        amount=5,
        nonce=0,
    )

    graph = RelevanceGraph.build(
        {
            "nonce:alice": {
                f"event:{visible.event_id()}",
                f"event:{hidden.event_id()}",
            }
        }
    )

    node = Node(
        node_id="TEST-NODE",
        relevance_graph=graph,
    )

    node.events.append(visible)

    before = node.status()

    assert before != DecisionStatus.UNIQUE, (
        "A node must not finalize UNIQUE while a "
        "semantically relevant event remains unknown."
    )

    node.events.append(hidden)

    after = node.status()

    assert after == DecisionStatus.CONFLICTED
