from core.event import Transfer
from core.graph_resolution import GraphResolver
from core.precedence import PrecedenceAttestation
from core.precedence_graph import PrecedenceGraph
from core.state import State


def build_graph(event_a, event_b):
    # Nessuna precedenza tra A e B:
    # sono concorrenti.
    return PrecedenceGraph()


def derive_node_state(events, graph):
    resolved = GraphResolver.resolve(events, graph)

    state = State(
        balances={
            "alice": 10,
            "bob": 0,
            "carol": 0,
        },
        nonces={
            "alice": 0,
            "bob": 0,
            "carol": 0,
        },
    )

    # Qui usiamo l'attuale derivazione deterministica.
    from core.derive import StateDeriver

    return StateDeriver.apply_events(
        state,
        resolved,
    )


def test_two_nodes_with_same_information_derive_same_state():
    event_a = Transfer(
        sender="alice",
        receiver="bob",
        amount=5,
        nonce=0,
    )

    event_b = Transfer(
        sender="alice",
        receiver="carol",
        amount=5,
        nonce=0,
    )

    graph_a = build_graph(event_a, event_b)
    graph_b = build_graph(event_a, event_b)

    events = [event_a, event_b]

    try:
        state_a = derive_node_state(events, graph_a)
        state_b = derive_node_state(events, graph_b)
    except ValueError:
        # Un double-spend deve essere rifiutato:
        # il sistema non può derivare due stati diversi
        # accettando entrambe le transazioni.
        return

    assert state_a.root() == state_b.root()
