from core.event import Transfer
from core.snapshot import GraphSnapshot
from core.snapshot_compat import compatible
from core.state import State
from core.state_proof import StateProof


def test_two_valid_conflicting_snapshots_have_no_intrinsic_winner():
    initial = State(
        balances={"alice": 10},
        nonces={"alice": 0},
    )

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

    snapshot_a = GraphSnapshot(
        events=(tx_a,),
        frontier=frozenset({tx_a.event_id()}),
    )

    snapshot_b = GraphSnapshot(
        events=(tx_b,),
        frontier=frozenset({tx_b.event_id()}),
    )

    assert not compatible(snapshot_a, snapshot_b)

    state_a = StateProof(
        state_root=State(
            balances={"alice": 2, "bob": 8},
            nonces={"alice": 1},
        ).root(),
        events=(tx_a,),
    )

    state_b = StateProof(
        state_root=State(
            balances={"alice": 2, "carol": 8},
            nonces={"alice": 1},
        ).root(),
        events=(tx_b,),
    )

    assert state_a.verify(initial)
    assert state_b.verify(initial)

    assert state_a.state_root != state_b.state_root
