from core.event import Transfer
from core.state import State
from core.relevance_proof import build_relevance_proof


def test_hidden_event_can_invalidate_local_relevance_claim():
    initial = State(
        balances={"alice": 10},
        nonces={"alice": 0},
    )

    visible = Transfer(
        sender="alice",
        receiver="bob",
        amount=3,
        nonce=0,
    )

    hidden_conflicting = Transfer(
        sender="alice",
        receiver="carol",
        amount=8,
        nonce=0,
    )

    # Nodo A conosce soltanto l'evento visible.
    proof = build_relevance_proof(
        initial,
        [visible],
    )

    # Nodo A può verificare correttamente ciò che conosce.
    assert proof.verify(
        initial,
        [visible],
    )

    # Ma esiste un evento nascosto che usa lo stesso
    # nonce e quindi rappresenta un'alternativa incompatibile.
    assert hidden_conflicting.nonce == visible.nonce
    assert hidden_conflicting.sender == visible.sender
    assert hidden_conflicting.event_id() != visible.event_id()

    # La prova locale NON contiene alcuna informazione
    # sull'evento nascosto.
    assert hidden_conflicting.event_id() not in proof.relevant_event_ids


def test_hidden_event_changes_possible_future_state():
    initial = State(
        balances={"alice": 10},
        nonces={"alice": 0},
    )

    visible = Transfer(
        sender="alice",
        receiver="bob",
        amount=3,
        nonce=0,
    )

    hidden = Transfer(
        sender="alice",
        receiver="carol",
        amount=8,
        nonce=0,
    )

    proof = build_relevance_proof(
        initial,
        [visible],
    )

    assert proof.verify(
        initial,
        [visible],
    )

    # Entrambe le alternative sono localmente valide
    # rispetto allo stesso stato iniziale.
    assert proof.verify(
        initial,
        [visible],
    )

    hidden_proof = build_relevance_proof(
        initial,
        [hidden],
    )

    assert hidden_proof.verify(
        initial,
        [hidden],
    )

    # Le due alternative producono stati differenti.
    assert visible.event_id() != hidden.event_id()
    assert proof.state_root == hidden_proof.state_root
    assert proof.relevant_event_ids != hidden_proof.relevant_event_ids
