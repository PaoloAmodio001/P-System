from core.event import Transfer
from core.causality import CausalGraph


def test_causal_graph_cannot_intrinsically_resolve_concurrent_double_spend():
    graph = CausalGraph()

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

    id_a = graph.add(tx_a)
    id_b = graph.add(tx_b)

    # I due eventi sono entrambi presenti nel grafo.
    assert graph.contains(id_a)
    assert graph.contains(id_b)

    # Nessuno dei due è causalmente successivo all'altro.
    assert id_a not in graph.ancestors(id_b)
    assert id_b not in graph.ancestors(id_a)

    # Entrambi sono eventi concorrenti.
    assert tx_a.nonce == tx_b.nonce
    assert tx_a.sender == tx_b.sender
    assert tx_a != tx_b
