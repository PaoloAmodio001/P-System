from core.event import Transfer
from core.relevance_graph import RelevanceGraph
from core.uncertainty_boundary import (
    RelevanceStatus,
    analyze_boundary,
)


def test_hidden_transfer_creates_uncertainty_boundary():
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

    hidden_child = Transfer(
        sender="carol",
        receiver="dave",
        amount=2,
        nonce=0,
        parents=(hidden.event_id(),),
    )

    # Il nodo conosce solamente l'evento visibile.
    known_event = f"event:{visible.event_id()}"

    # Il dominio di rilevanza locale contiene il nonce
    # che può essere coinvolto nel conflitto.
    root = "nonce:alice"

    graph = RelevanceGraph.build(
        {
            root: {known_event},
            known_event: {f"conflict:{hidden.event_id()}"},
            f"conflict:{hidden.event_id()}": {
                f"event:{hidden_child.event_id()}"
            },
        }
    )

    boundary = analyze_boundary(
        {root, known_event},
        graph,
    )

    assert boundary.status(
        f"conflict:{hidden.event_id()}"
    ) == RelevanceStatus.POTENTIALLY_RELEVANT

    assert boundary.status(
        f"event:{hidden_child.event_id()}"
    ) == RelevanceStatus.POTENTIALLY_RELEVANT


def test_hidden_conflicting_transfer_cannot_be_called_irrelevant():
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

    assert visible.sender == hidden.sender
    assert visible.nonce == hidden.nonce
    assert visible.event_id() != hidden.event_id()

    graph = RelevanceGraph.build(
        {
            "nonce:alice": {
                f"event:{visible.event_id()}",
                f"event:{hidden.event_id()}",
            }
        }
    )

    boundary = analyze_boundary(
        {
            "nonce:alice",
            f"event:{visible.event_id()}",
        },
        graph,
    )

    assert boundary.status(
        f"event:{hidden.event_id()}"
    ) == RelevanceStatus.POTENTIALLY_RELEVANT

    assert f"event:{hidden.event_id()}" not in (
        boundary.irrelevant
    )


def test_unrelated_hidden_transfer_can_remain_outside_boundary():
    visible = Transfer(
        sender="alice",
        receiver="bob",
        amount=3,
        nonce=0,
    )

    unrelated = Transfer(
        sender="carol",
        receiver="dave",
        amount=2,
        nonce=0,
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

    boundary = analyze_boundary(
        {
            "nonce:alice",
            f"event:{visible.event_id()}",
        },
        graph,
    )

    assert boundary.status(
        f"event:{unrelated.event_id()}"
    ) == RelevanceStatus.IRRELEVANT
