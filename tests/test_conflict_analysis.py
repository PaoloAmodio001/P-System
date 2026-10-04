from core.conflict_analysis import analyze
from core.conflict_set import ConflictCandidate, ConflictSet
from core.event import Transfer
from core.state import State
from core.state_proof import StateProof
from core.derive import StateDeriver


def test_conflict_analysis_does_not_choose_winner():
    initial = State({
        "alice": 10,
        "bob": 0,
        "carol": 0,
    })

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

    state_a = StateDeriver.apply_events(
        initial,
        [tx_a],
    )

    state_b = StateDeriver.apply_events(
        initial,
        [tx_b],
    )

    conflict_set = ConflictSet(
        candidates=(
            ConflictCandidate(
                name="A",
                state_root=state_a.root(),
                events=(tx_a,),
            ),
            ConflictCandidate(
                name="B",
                state_root=state_b.root(),
                events=(tx_b,),
            ),
        )
    )

    analysis = analyze(
        conflict_set,
        initial,
    )

    assert analysis.valid_candidates == ("A", "B")
    assert analysis.conflicting
    assert analysis.winner is None
    assert not analysis.has_winner


def test_single_valid_candidate_has_no_conflict():
    initial = State({
        "alice": 10,
        "bob": 0,
    })

    tx = Transfer(
        "alice",
        "bob",
        5,
        0,
    )

    state = StateDeriver.apply_events(
        initial,
        [tx],
    )

    conflict_set = ConflictSet(
        candidates=(
            ConflictCandidate(
                name="A",
                state_root=state.root(),
                events=(tx,),
            ),
        )
    )

    analysis = analyze(
        conflict_set,
        initial,
    )

    assert analysis.valid_candidates == ("A",)
    assert not analysis.conflicting
    assert analysis.winner is None


def test_invalid_candidates_are_not_selected():
    initial = State({
        "alice": 10,
        "bob": 0,
    })

    tx = Transfer(
        "alice",
        "bob",
        5,
        0,
    )

    conflict_set = ConflictSet(
        candidates=(
            ConflictCandidate(
                name="INVALID",
                state_root="not-a-real-root",
                events=(tx,),
            ),
        )
    )

    analysis = analyze(
        conflict_set,
        initial,
    )

    assert analysis.valid_candidates == ()
    assert not analysis.conflicting
    assert analysis.winner is None
