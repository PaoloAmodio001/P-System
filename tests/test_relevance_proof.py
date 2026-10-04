from core.event import Transfer
from core.state import State
from core.relevance_proof import build_relevance_proof


def test_relevance_proof_detects_applicable_event():
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

    proof = build_relevance_proof(
        state,
        [event],
    )

    assert event.event_id() in proof.relevant_event_ids
    assert proof.verify(state, [event])


def test_relevance_proof_ignores_invalid_event():
    state = State(
        balances={"alice": 10},
        nonces={"alice": 0},
    )

    event = Transfer(
        sender="alice",
        receiver="bob",
        amount=20,
        nonce=0,
    )

    proof = build_relevance_proof(
        state,
        [event],
    )

    assert event.event_id() not in proof.relevant_event_ids
    assert proof.verify(state, [event])


def test_relevance_proof_cannot_claim_unknown_relevant_event_is_known():
    state = State(
        balances={"alice": 10},
        nonces={"alice": 0},
    )

    known_event = Transfer(
        sender="alice",
        receiver="bob",
        amount=3,
        nonce=0,
    )

    unknown_event = Transfer(
        sender="alice",
        receiver="carol",
        amount=4,
        nonce=0,
    )

    proof = build_relevance_proof(
        state,
        [known_event],
    )

    assert unknown_event.event_id() not in proof.relevant_event_ids

    assert not proof.verify(
        state,
        [unknown_event],
    )
