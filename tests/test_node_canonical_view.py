from core.event import Transfer
from core.state import State
from network.node import Node


def _node(initial, events, local_state=None):
    # Evita di avviare server o connessioni: qui testiamo soltanto la vista.
    node = Node.__new__(Node)
    node._initial_state = initial.copy()
    node.events = list(events)
    node.state = (local_state or initial).copy()
    return node


def test_canonical_view_is_independent_of_event_arrival_order():
    initial = State(
        balances={"alice": 10, "carol": 10},
        nonces={"alice": 0, "carol": 0},
    )
    alice_tx = Transfer("alice", "bob", 3, 0)
    carol_tx = Transfer("carol", "dave", 2, 0)

    node_a = _node(initial, [alice_tx, carol_tx])
    node_b = _node(initial, [carol_tx, alice_tx])

    view_a = node_a.canonical_view()
    view_b = node_b.canonical_view()

    assert view_a.is_unique()
    assert view_b.is_unique()
    assert view_a.state.root() == view_b.state.root()


def test_canonical_view_reports_conflict_without_mutating_local_state():
    initial = State(
        balances={"alice": 10},
        nonces={"alice": 0},
    )
    first = Transfer("alice", "bob", 3, 0)
    second = Transfer("alice", "carol", 4, 0)

    local_a = State(
        balances={"alice": 7, "bob": 3},
        nonces={"alice": 1},
    )
    local_b = State(
        balances={"alice": 6, "carol": 4},
        nonces={"alice": 1},
    )
    node_a = _node(initial, [first, second], local_a)
    node_b = _node(initial, [second, first], local_b)
    root_a_before = node_a.state_root()
    root_b_before = node_b.state_root()

    view_a = node_a.canonical_view()
    view_b = node_b.canonical_view()

    assert view_a.is_ambiguous()
    assert view_b.is_ambiguous()
    assert not view_a.has_winner()
    assert not view_b.has_winner()
    assert set(view_a.alternatives()) == {first, second}
    assert set(view_b.alternatives()) == {first, second}

    # La vista canonica non altera la proiezione operativa locale.
    assert node_a.state_root() == root_a_before
    assert node_b.state_root() == root_b_before
