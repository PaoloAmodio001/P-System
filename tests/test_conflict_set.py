from core.conflict_set import ConflictCandidate, ConflictSet
from core.event import Transfer
from core.state import State
from core.state_proof import StateProof


def test_conflict_set_contains_multiple_valid_candidates():
    initial = State(
        balances={"alice": 10},
        nonces={"alice": 0},
    )

    event_a = Transfer(
        sender="alice",
        receiver="bob",
        amount=8,
        nonce=0,
    )

    event_b = Transfer(
        sender="alice",
        receiver="carol",
        amount=8,
        nonce=0,
    )

    state_a = State(
        balances={"alice": 2, "bob": 8},
        nonces={"alice": 1},
    )

    state_b = State(
        balances={"alice": 2, "carol": 8},
        nonces={"alice": 1},
    )

    candidate_a = ConflictCandidate(
        name="A",
        state_root=state_a.root(),
        events=(event_a,),
    )

    candidate_b = ConflictCandidate(
        name="B",
        state_root=state_b.root(),
        events=(event_b,),
    )

    conflict_set = ConflictSet(
        candidates=(candidate_a, candidate_b),
    )

    assert candidate_a.verify(initial)
    assert candidate_b.verify(initial)

    assert conflict_set.valid_candidates(initial) == ("A", "B")
    assert conflict_set.has_conflict(initial)


def test_conflict_set_rejects_invalid_candidate():
    initial = State(
        balances={"alice": 10},
        nonces={"alice": 0},
    )

    event = Transfer(
        sender="alice",
        receiver="bob",
        amount=8,
        nonce=0,
    )

    invalid_candidate = ConflictCandidate(
        name="INVALID",
        state_root="0" * 64,
        events=(event,),
    )

    conflict_set = ConflictSet(
        candidates=(invalid_candidate,),
    )

    assert conflict_set.valid_candidates(initial) == ()
    assert not conflict_set.has_conflict(initial)
