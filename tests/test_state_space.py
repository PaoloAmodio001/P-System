from core.conflict_set import ConflictCandidate
from core.event import Transfer
from core.derive import StateDeriver
from core.state import State
from core.state_space import StateSpace


def test_state_space_can_contain_multiple_valid_states():
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

    space = StateSpace(
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

    assert space.valid(initial) == ("A", "B")
    assert space.contains_multiple_valid_states(initial)


def test_state_space_has_no_winner():
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

    state_a = StateDeriver.apply_events(initial, [tx_a])
    state_b = StateDeriver.apply_events(initial, [tx_b])

    space = StateSpace(
        candidates=(
            ConflictCandidate(
                "A",
                state_a.root(),
                (tx_a,),
            ),
            ConflictCandidate(
                "B",
                state_b.root(),
                (tx_b,),
            ),
        )
    )

    assert not hasattr(space, "winner")


def test_same_state_is_equivalent():
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

    candidate_a = ConflictCandidate(
        "A",
        state.root(),
        (tx,),
    )

    candidate_b = ConflictCandidate(
        "B",
        state.root(),
        (tx,),
    )

    space = StateSpace(
        candidates=(candidate_a, candidate_b)
    )

    relations = space.relations()

    assert len(relations) == 1
    assert relations[0].relation == "EQUIVALENT"


def test_different_states_are_distinct():
    initial = State({
        "alice": 10,
        "bob": 0,
        "carol": 0,
    })

    tx_a = Transfer(
        "alice",
        "bob",
        5,
        0,
    )

    tx_b = Transfer(
        "alice",
        "carol",
        5,
        0,
    )

    state_a = StateDeriver.apply_events(initial, [tx_a])
    state_b = StateDeriver.apply_events(initial, [tx_b])

    space = StateSpace(
        candidates=(
            ConflictCandidate(
                "A",
                state_a.root(),
                (tx_a,),
            ),
            ConflictCandidate(
                "B",
                state_b.root(),
                (tx_b,),
            ),
        )
    )

    relations = space.relations()

    assert len(relations) == 1
    assert relations[0].relation == "DISTINCT"


def test_empty_state_space_has_no_valid_states():
    initial = State({
        "alice": 10,
    })

    space = StateSpace(
        candidates=()
    )

    assert space.names() == ()
    assert space.valid(initial) == ()
    assert not space.contains_multiple_valid_states(initial)
