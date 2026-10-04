from core.event import Transfer
from core.relevance import (
    RelevanceNode,
    build_relevance_region,
)
from core.state import State


def test_transfer_creates_real_state_relevance_nodes():
    state = State(
        balances={"alice": 10},
        nonces={"alice": 0},
    )

    event = Transfer(
        sender="alice",
        receiver="bob",
        amount=3,
        nonce=0,
    )

    region = build_relevance_region(
        state,
        [event],
    )

    assert region.contains(
        RelevanceNode("balance", "alice")
    )

    assert region.contains(
        RelevanceNode("balance", "bob")
    )

    assert region.contains(
        RelevanceNode("nonce", "alice")
    )

    assert region.contains(
        RelevanceNode("event", event.event_id())
    )


def test_unrelated_event_is_outside_local_region():
    state = State(
        balances={
            "alice": 10,
            "carol": 10,
        },
        nonces={
            "alice": 0,
            "carol": 0,
        },
    )

    visible = Transfer(
        sender="alice",
        receiver="bob",
        amount=3,
        nonce=0,
    )

    hidden = Transfer(
        sender="carol",
        receiver="dave",
        amount=2,
        nonce=0,
    )

    region = build_relevance_region(
        state,
        [visible],
    )

    assert not region.contains(
        RelevanceNode("balance", "carol")
    )

    assert not region.contains(
        RelevanceNode("balance", "dave")
    )

    assert not region.contains(
        RelevanceNode("event", hidden.event_id())
    )


def test_conflicting_transfer_touches_same_nonce_domain():
    state = State(
        balances={"alice": 10},
        nonces={"alice": 0},
    )

    first = Transfer(
        sender="alice",
        receiver="bob",
        amount=3,
        nonce=0,
    )

    second = Transfer(
        sender="alice",
        receiver="carol",
        amount=5,
        nonce=0,
    )

    region = build_relevance_region(
        state,
        [first],
    )

    assert region.contains(
        RelevanceNode("nonce", "alice")
    )

    assert region.contains(
        RelevanceNode("balance", "alice")
    )

    assert second.event_id() not in {
        node.identifier
        for node in region.nodes
        if node.kind == "event"
    }
