from core.event import Transfer
from core.causality import CausalGraph


def test_causality_distinguishes_order_from_concurrency():
    graph = CausalGraph()

    tx_0 = Transfer(
        sender="alice",
        receiver="bob",
        amount=5,
        nonce=0,
    )

    tx_1 = Transfer(
        sender="bob",
        receiver="carol",
        amount=3,
        nonce=0,
        parents=(tx_0.event_id(),),
    )

    tx_parallel = Transfer(
        sender="dave",
        receiver="erin",
        amount=2,
        nonce=0,
    )

    id_0 = graph.add(tx_0)
    id_1 = graph.add(tx_1)
    id_parallel = graph.add(tx_parallel)

    assert id_0 in graph.ancestors(id_1)

    assert id_parallel not in graph.ancestors(id_1)

    assert id_0 not in graph.ancestors(id_parallel)

    assert id_1 not in graph.ancestors(id_parallel)
