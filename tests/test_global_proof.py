from core.state import State
from core.event import Transfer
from core.derive import StateDeriver
from core.global_proof import GlobalStateProof


def test_global_proof_valid():

    initial = State({
        "alice": 10,
        "bob": 0,
    })

    events = (
        Transfer(
            "alice",
            "bob",
            5,
            0,
        ),
    )

    state = StateDeriver.apply_events(
        initial,
        list(events),
    )

    proof = GlobalStateProof(
        state_root=state.root(),
        events=events,
        witnesses=frozenset({
            "node-1",
            "node-2",
            "node-3",
        }),
    )

    assert proof.verify(initial)


def test_global_proof_without_witnesses_rejected():

    initial = State({
        "alice": 10,
        "bob": 0,
    })

    events = (
        Transfer(
            "alice",
            "bob",
            5,
            0,
        ),
    )

    state = StateDeriver.apply_events(
        initial,
        list(events),
    )

    proof = GlobalStateProof(
        state_root=state.root(),
        events=events,
        witnesses=frozenset(),
    )

    assert not proof.verify(initial)


def test_conflicting_global_proof_rejected():

    initial = State({
        "alice": 10,
        "bob": 0,
        "carol": 0,
    })

    events = (
        Transfer("alice", "bob", 8, 0),
        Transfer("alice", "carol", 8, 0),
    )

    proof = GlobalStateProof(
        state_root="00" * 32,
        events=events,
        witnesses=frozenset({
            "node-1",
            "node-2",
            "node-3",
        }),
    )

    assert not proof.verify(initial)
