from core.state import State
from core.event import Transfer
from core.derive import StateDeriver
from core.global_proof import GlobalStateProof
from core.decision import distinguish


def test_two_valid_conflicting_states_are_indistinguishable():

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

    proof_a = GlobalStateProof(
        state_root=state_a.root(),
        events=(tx_a,),
        witnesses=frozenset({"node-a"}),
    )

    proof_b = GlobalStateProof(
        state_root=state_b.root(),
        events=(tx_b,),
        witnesses=frozenset({"node-b"}),
    )

    assert proof_a.verify(initial)
    assert proof_b.verify(initial)

    assert proof_a.state_root != proof_b.state_root

    # There is currently no intrinsic rule that
    # distinguishes one valid state as globally authoritative.
    assert not distinguish(proof_a, proof_b)
