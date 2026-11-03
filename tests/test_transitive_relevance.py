from itertools import permutations

import pytest

from core.block_propagation import propagate_blocked
from core.dependency_graph import DependencyGraph
from core.derive import StateDeriver
from core.event import Transfer
from core.incompatibility import incompatible
from core.proof import apply_transfer, verify_transfer
from core.relevance_proof import build_relevance_proof
from core.resolver import ConflictResolver
from core.state import State


def _ids(*events: Transfer) -> set[str]:
    return {event.event_id() for event in events}


@pytest.fixture
def chain():
    """alice -> bob -> carol -> dave, ogni anello dichiara il precedente."""
    state = State(
        balances={"alice": 10, "bob": 0, "carol": 0},
        nonces={"alice": 0, "bob": 0, "carol": 0},
    )
    hidden_a = Transfer(sender="alice", receiver="bob", amount=5, nonce=0)
    hidden_b = Transfer(
        sender="bob",
        receiver="carol",
        amount=3,
        nonce=0,
        parents=(hidden_a.event_id(),),
    )
    hidden_c = Transfer(
        sender="carol",
        receiver="dave",
        amount=2,
        nonce=0,
        parents=(hidden_b.event_id(),),
    )
    return state, hidden_a, hidden_b, hidden_c


def test_hidden_event_can_become_relevant_through_hidden_predecessor():
    state = State(
        balances={"alice": 10, "bob": 0},
        nonces={"alice": 0, "bob": 0},
    )
    hidden_a = Transfer(sender="alice", receiver="bob", amount=4, nonce=0)
    hidden_b = Transfer(
        sender="bob",
        receiver="carol",
        amount=2,
        nonce=0,
        parents=(hidden_a.event_id(),),
    )

    # Da solo hidden_b non è valido: Bob non ha fondi.
    assert not verify_transfer(state, hidden_b)
    with pytest.raises(ValueError):
        apply_transfer(state, hidden_b)

    # Rispetto allo stato corrente solo hidden_a risulta rilevante...
    proof = build_relevance_proof(state, [hidden_a, hidden_b])
    assert proof.relevant_event_ids == _ids(hidden_a)
    assert proof.verify(state, [hidden_a, hidden_b])

    # ...ma hidden_b non può essere considerato senza il suo predecessore.
    with pytest.raises(ValueError, match="UNKNOWN PARENT"):
        DependencyGraph.build([hidden_b])
    with pytest.raises(ValueError, match="UNKNOWN PARENT"):
        StateDeriver.apply_events(state, [hidden_b])

    # Con il predecessore la storia è valida, in qualunque ordine arrivi.
    for order in permutations([hidden_a, hidden_b]):
        derived = StateDeriver.apply_events(state, list(order))
        assert derived.balances == {"alice": 6, "bob": 2, "carol": 2}
        assert derived.nonce("alice") == 1
        assert derived.nonce("bob") == 1


def test_implicit_funding_dependency_is_resolved_without_parents():
    # Nessun parent dichiarato: la dipendenza è solo nei saldi.
    state = State(balances={"alice": 10, "bob": 0}, nonces={})
    funding = Transfer(sender="alice", receiver="bob", amount=4, nonce=0)
    spend = Transfer(sender="bob", receiver="carol", amount=3, nonce=0)

    with pytest.raises(ValueError):
        StateDeriver.apply_events(state, [spend])

    for order in permutations([funding, spend]):
        derived = StateDeriver.apply_events(state, list(order))
        assert derived.balances == {"alice": 6, "bob": 1, "carol": 3}


def test_transitive_dependency_makes_hidden_chain_relevant(chain):
    state, hidden_a, hidden_b, hidden_c = chain
    full = [hidden_a, hidden_b, hidden_c]

    graph = DependencyGraph.build(full)
    assert graph.parents_of(hidden_b.event_id()) == _ids(hidden_a)
    assert graph.parents_of(hidden_c.event_id()) == _ids(hidden_b)
    assert not graph.has_cycle()

    # La catena viene sbloccata un anello alla volta.
    assert graph.ready(set()) == _ids(hidden_a)
    assert graph.ready(_ids(hidden_a)) == _ids(hidden_b)
    assert graph.ready(_ids(hidden_a, hidden_b)) == _ids(hidden_c)

    # hidden_c dipende transitivamente da hidden_a: senza un qualunque
    # anello intermedio la storia non è derivabile.
    for missing in (hidden_a, hidden_b):
        partial = [event for event in full if event is not missing]
        with pytest.raises(ValueError, match="UNKNOWN PARENT"):
            StateDeriver.apply_events(state, partial)

    expected = {"alice": 5, "bob": 2, "carol": 1, "dave": 2}
    for order in permutations(full):
        assert StateDeriver.apply_events(state, list(order)).balances == expected


def test_blocking_the_root_blocks_the_whole_hidden_chain(chain):
    _, hidden_a, hidden_b, hidden_c = chain
    full = [hidden_a, hidden_b, hidden_c]

    assert propagate_blocked(full, _ids(hidden_a)) == _ids(*full)
    # Il blocco segue solo i discendenti, non gli antenati.
    assert propagate_blocked(full, _ids(hidden_b)) == _ids(hidden_b, hidden_c)


def test_visible_conflict_does_not_remove_hidden_causal_relevance():
    state = State(
        balances={"alice": 10, "bob": 0, "carol": 0},
        nonces={"alice": 0, "bob": 0, "carol": 0},
    )
    visible = Transfer(sender="alice", receiver="bob", amount=3, nonce=0)
    hidden = Transfer(sender="alice", receiver="carol", amount=5, nonce=0)
    hidden_child = Transfer(
        sender="carol",
        receiver="dave",
        amount=2,
        nonce=0,
        parents=(hidden.event_id(),),
    )

    # Visible e hidden sono alternative incompatibili (stesso sender e nonce).
    assert incompatible(visible, hidden)
    assert not ConflictResolver.compatible([visible, hidden])
    with pytest.raises(ValueError, match="CONFLICTING EVENTS"):
        StateDeriver.apply_events(state, [visible, hidden, hidden_child])

    # Il figlio non è in conflitto con visible, ma resta legato all'alternativa
    # nascosta: senza hidden non è derivabile...
    assert not incompatible(visible, hidden_child)
    with pytest.raises(ValueError, match="UNKNOWN PARENT"):
        StateDeriver.apply_events(state, [visible, hidden_child])

    # ...e se il conflitto blocca le alternative, il blocco lo raggiunge.
    all_events = [visible, hidden, hidden_child]
    blocked = propagate_blocked(all_events, _ids(visible, hidden))
    assert hidden_child.event_id() in blocked

    # Scegliendo l'alternativa nascosta, il figlio torna eseguibile.
    derived = StateDeriver.apply_events(state, [hidden_child, hidden])
    assert derived.balances == {"alice": 5, "bob": 0, "carol": 3, "dave": 2}
