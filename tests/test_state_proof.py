from core.state import State
from core.event import Transfer
from core.derive import StateDeriver
from core.state_proof import StateProof


def test_valid_state_proof():

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

    proof = StateProof(
        state_root=state.root(),
        events=events,
    )

    assert proof.verify(initial)


def test_tampered_state_root_rejected():

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

    proof = StateProof(
        state_root="00" * 32,
        events=events,
    )

    assert not proof.verify(initial)


def test_conflicting_state_proof_rejected():

    initial = State({
        "alice": 10,
        "bob": 0,
        "carol": 0,
    })

    events = (
        Transfer("alice", "bob", 8, 0),
        Transfer("alice", "carol", 8, 0),
    )

    proof = StateProof(
        state_root="00" * 32,
        events=events,
    )

    assert not proof.verify(initial)
