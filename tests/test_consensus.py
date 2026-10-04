from core.state import State
from core.event import Transfer
from core.proof import apply_transfer
from core.global_proof import GlobalStateProof
from core.consensus import distinguish


def test_valid_conflicting_states_have_no_intrinsic_winner():
    initial = State({
        "alice": 10,
        "bob": 0,
        "carol": 0,
    })

    tx_a = Transfer(
        sender="alice",
        receiver="bob",
        amount=8,
        nonce=0,
    )

    tx_b = Transfer(
        sender="alice",
        receiver="carol",
        amount=8,
        nonce=0,
    )

    state_a = apply_transfer(initial, tx_a)
    state_b = apply_transfer(initial, tx_b)

    proof_a = GlobalStateProof(
        state_root=state_a.root(),
        events=(tx_a,),
        witnesses=frozenset({"node-1", "node-2", "node-3"}),
    )

    proof_b = GlobalStateProof(
        state_root=state_b.root(),
        events=(tx_b,),
        witnesses=frozenset({"node-4", "node-5", "node-6"}),
    )

    assert proof_a.verify(initial)
    assert proof_b.verify(initial)

    decision = distinguish(proof_a, proof_b)

    assert decision.accepted is False
    assert decision.reason == "INSUFFICIENT_INFORMATION"

def test_invalid_candidate_is_rejected_when_initial_state_is_known():
    initial = State({
        "alice": 10,
        "bob": 0,
        "carol": 0,
    })

    tx = Transfer(
        sender="alice",
        receiver="bob",
        amount=8,
        nonce=0,
    )

    valid_state = apply_transfer(initial, tx)

    valid = GlobalStateProof(
        state_root=valid_state.root(),
        events=(tx,),
        witnesses=frozenset({"node-1"}),
    )

    invalid = GlobalStateProof(
        state_root="0" * 64,
        events=(tx,),
        witnesses=frozenset({"node-2"}),
    )

    decision = distinguish(
        valid,
        invalid,
        initial_state=initial,
    )

    assert decision.accepted is False
    assert decision.reason == "INVALID_CANDIDATE"


def test_valid_different_states_remain_without_winner():
    initial = State({
        "alice": 10,
        "bob": 0,
        "carol": 0,
    })

    tx_a = Transfer(
        sender="alice",
        receiver="bob",
        amount=8,
        nonce=0,
    )

    tx_b = Transfer(
        sender="alice",
        receiver="carol",
        amount=8,
        nonce=0,
    )

    state_a = apply_transfer(initial, tx_a)
    state_b = apply_transfer(initial, tx_b)

    proof_a = GlobalStateProof(
        state_root=state_a.root(),
        events=(tx_a,),
        witnesses=frozenset({"node-1"}),
    )

    proof_b = GlobalStateProof(
        state_root=state_b.root(),
        events=(tx_b,),
        witnesses=frozenset({"node-2"}),
    )

    decision = distinguish(
        proof_a,
        proof_b,
        initial_state=initial,
    )

    assert decision.accepted is False
    assert decision.reason == "INSUFFICIENT_INFORMATION"
