from core.state import State
from core.event import Transfer
from simulator.network import create_network


def test_conflicting_transactions():
    nodes = create_network(
        5,
        State({"alice": 10})
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

    # Network partition:
    group_a = nodes[:3]
    group_b = nodes[3:]

    for node in group_a:
        assert node.receive(tx_a)

    for node in group_b:
        assert node.receive(tx_b)

    roots_a = {node.state_root() for node in group_a}
    roots_b = {node.state_root() for node in group_b}

    assert len(roots_a) == 1
    assert len(roots_b) == 1

    # The network has now split into two valid-looking states.
    assert roots_a != roots_b
