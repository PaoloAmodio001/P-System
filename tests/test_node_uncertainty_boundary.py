from core.decision_status import DecisionStatus
from core.event import Transfer
from core.relevance_graph import RelevanceGraph
from core.uncertainty_boundary import analyze_boundary
from core.relevance import transfer_nodes
from core.state import State
from network.node import Node


def test_relevant_unknown_event_makes_boundary_uncertain():
    visible = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    hidden = Transfer(
        "alice",
        "carol",
        5,
        0,
    )

    visible_nodes = transfer_nodes(visible)

    graph = RelevanceGraph.build(
        {
            "nonce:alice": {
                f"event:{visible.event_id()}",
                f"event:{hidden.event_id()}",
            }
        }
    )

    boundary = analyze_boundary(
        {node.key() for node in visible_nodes},
        graph,
    )

    assert f"event:{hidden.event_id()}" in boundary.potentially_relevant

    node = Node(
        "node-A",
        State({"alice": 10}),
    )

    assert node.receive(visible)
    assert node.status() == DecisionStatus.UNIQUE

    # The node itself cannot yet see the hidden event.
    assert hidden not in node.events

    # The relevance model nevertheless proves that this domain
    # contains potentially relevant unknown information.
    assert f"event:{hidden.event_id()}" in boundary.potentially_relevant


def test_unrelated_unknown_event_does_not_make_boundary_uncertain():
    visible = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    unrelated = Transfer(
        "carol",
        "dave",
        5,
        0,
    )

    graph = RelevanceGraph.build(
        {
            "nonce:alice": {
                f"event:{visible.event_id()}",
            },
            "nonce:carol": {
                f"event:{unrelated.event_id()}",
            },
        }
    )

    visible_nodes = transfer_nodes(visible)

    boundary = analyze_boundary(
        {node.key() for node in visible_nodes},
        graph,
    )

    assert f"event:{unrelated.event_id()}" not in boundary.potentially_relevant
    assert f"event:{unrelated.event_id()}" in boundary.irrelevant
