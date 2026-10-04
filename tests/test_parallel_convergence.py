from core.event import Transfer
from core.graph_resolution import GraphResolver
from core.precedence_graph import PrecedenceGraph
from core.state import State
from core.derive import StateDeriver


def derive(events, graph):
    resolved = GraphResolver.resolve(events, graph)

    initial = State(
        balances={
            "alice": 10,
            "carol": 10,
        },
        nonces={
            "alice": 0,
            "carol": 0,
        },
    )

    return StateDeriver.apply_events(
        initial,
        resolved,
    )


def test_independent_nodes_converge_to_same_state():
    event_a = Transfer(
        sender="alice",
        receiver="bob",
        amount=5,
        nonce=0,
    )

    event_b = Transfer(
        sender="carol",
        receiver="dave",
        amount=7,
        nonce=0,
    )

    graph_a = PrecedenceGraph()
    graph_b = PrecedenceGraph()

    events_a = [event_a, event_b]
    events_b = [event_b, event_a]

    state_a = derive(events_a, graph_a)
    state_b = derive(events_b, graph_b)

    assert state_a.root() == state_b.root()

    assert state_a.balance("alice") == 5
    assert state_a.balance("bob") == 5
    assert state_a.balance("carol") == 3
    assert state_a.balance("dave") == 7
