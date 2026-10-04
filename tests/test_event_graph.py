from core.state import State
from core.event import Transfer
from core.derive import StateDeriver
from core.resolver import ConflictResolver


def test_event_graph_separates_parallelism_from_conflict():
    initial = State({
        "alice": 20,
        "bob": 10,
        "carol": 0,
        "dave": 0,
        "eve": 0,
        "frank": 0,
    })

    tx_alice_carol = Transfer(
        "alice",
        "carol",
        4,
        0,
    )

    tx_bob_dave = Transfer(
        "bob",
        "dave",
        2,
        0,
    )

    tx_alice_eve = Transfer(
        "alice",
        "eve",
        3,
        1,
        parents=(tx_alice_carol.event_id(),),
    )

    tx_alice_frank = Transfer(
        "alice",
        "frank",
        5,
        0,
    )

    independent = [
        tx_alice_carol,
        tx_bob_dave,
        tx_alice_eve,
    ]

    conflicting = [
        tx_alice_carol,
        tx_alice_frank,
    ]

    assert ConflictResolver.compatible(independent)

    assert not ConflictResolver.compatible(conflicting)

    state = StateDeriver.apply_events(
        initial,
        independent,
    )

    assert state.balance("alice") == 13
    assert state.balance("bob") == 8
    assert state.balance("carol") == 4
    assert state.balance("dave") == 2
    assert state.balance("eve") == 3

    assert state.nonce("alice") == 2
    assert state.nonce("bob") == 1
