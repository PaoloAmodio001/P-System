from core.event import Transfer
from core.partial_knowledge import PartialKnowledge
from simulator.partition import NetworkPartition


def test_partition_nodes_can_have_different_knowledge():
    first = Transfer(
        "alice",
        "bob",
        4,
        0,
    )

    second = Transfer(
        "carol",
        "dave",
        3,
        0,
    )

    network = NetworkPartition({
        "node-a": PartialKnowledge(
            events=frozenset({first})
        ),
        "node-b": PartialKnowledge(
            events=frozenset({first})
        ),
    })

    network.add_event("node-a", first)
    network.add_event("node-b", second)

    assert network.knowledge(
        "node-a"
    ).event_ids() == frozenset({
        first.event_id(),
    })

    assert network.knowledge(
        "node-b"
    ).event_ids() == frozenset({
        first.event_id(),
        second.event_id(),
    })


def test_reconciliation_merges_knowledge():
    first = Transfer(
        "alice",
        "bob",
        4,
        0,
    )

    second = Transfer(
        "carol",
        "dave",
        3,
        0,
    )

    network = NetworkPartition({
        "node-a": PartialKnowledge(
            events=frozenset({first})
        ),
        "node-b": PartialKnowledge(
            events=frozenset({second})
        ),
    })

    network.reconcile(
        "node-a",
        "node-b",
    )

    expected = frozenset({
        first.event_id(),
        second.event_id(),
    })

    assert network.knowledge(
        "node-a"
    ).event_ids() == expected

    assert network.knowledge(
        "node-b"
    ).event_ids() == expected


def test_reconciliation_is_idempotent():
    first = Transfer(
        "alice",
        "bob",
        4,
        0,
    )

    network = NetworkPartition({
        "node-a": PartialKnowledge(
            events=frozenset({first})
        ),
        "node-b": PartialKnowledge(
            events=frozenset({first})
        ),
    })

    network.reconcile(
        "node-a",
        "node-b",
    )

    before = network.knowledge(
        "node-a"
    )

    network.reconcile(
        "node-a",
        "node-b",
    )

    after = network.knowledge(
        "node-a"
    )

    assert before == after


def test_partition_reconciliation_detects_concurrent_conflict():
    from core.partition_conflict import find_conflicts

    event_a = Transfer(
        "alice",
        "bob",
        6,
        0,
    )

    event_b = Transfer(
        "alice",
        "carol",
        7,
        0,
    )

    node_a = PartialKnowledge(
        events=frozenset({event_a})
    )

    node_b = PartialKnowledge(
        events=frozenset({event_b})
    )

    conflicts = find_conflicts(
        node_a,
        node_b,
    )

    assert len(conflicts) == 1
    assert conflicts[0].is_conflict()

    assert conflicts[0].first != conflicts[0].second


def test_conflict_state_preserves_alternatives_without_winner():
    from core.conflict_state import ConflictState

    event_a = Transfer(
        "alice",
        "bob",
        6,
        0,
    )

    event_b = Transfer(
        "alice",
        "carol",
        7,
        0,
    )

    state = ConflictState(
        alternatives=(event_a,)
    )

    state = state.add(event_b)

    assert state.contains(event_a)
    assert state.contains(event_b)

    assert state.is_conflicted()
    assert not state.has_winner()


def test_conflict_state_does_not_duplicate_event():
    from core.conflict_state import ConflictState

    event = Transfer(
        "alice",
        "bob",
        6,
        0,
    )

    state = ConflictState(
        alternatives=(event,)
    )

    state = state.add(event)

    assert state.alternatives == (event,)


def test_non_conflicting_alternatives_are_not_conflicted():
    from core.conflict_state import ConflictState

    first = Transfer(
        "alice",
        "bob",
        4,
        0,
    )

    second = Transfer(
        "carol",
        "dave",
        3,
        0,
    )

    state = ConflictState(
        alternatives=(first, second)
    )

    assert not state.is_conflicted()
    assert not state.has_winner()


def test_state_view_unique_state():
    from core.state import State
    from core.state_view import StateView

    state = State({
        "alice": 10,
        "bob": 0,
    })

    view = StateView.unique(state)

    assert view.is_unique()
    assert not view.is_ambiguous()
    assert not view.has_winner()
    assert view.alternatives() == ()


def test_state_view_ambiguous_state():
    from core.conflict_state import ConflictState
    from core.state_view import StateView

    event_a = Transfer(
        "alice",
        "bob",
        6,
        0,
    )

    event_b = Transfer(
        "alice",
        "carol",
        7,
        0,
    )

    conflict = ConflictState(
        alternatives=(event_a, event_b)
    )

    view = StateView.ambiguous(conflict)

    assert view.is_ambiguous()
    assert not view.is_unique()
    assert not view.has_winner()

    assert view.alternatives() == (
        event_a,
        event_b,
    )


def test_partition_reconciliation_preserves_independent_branches():
    from core.event import Transfer
    from core.partial_knowledge import PartialKnowledge
    from simulator.partition import NetworkPartition

    first = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    second = Transfer(
        "carol",
        "dave",
        2,
        0,
    )

    network = NetworkPartition(
        nodes={
            "node-a": PartialKnowledge(
                events=frozenset({first}),
            ),
            "node-b": PartialKnowledge(
                events=frozenset({second}),
            ),
        }
    )

    assert network.knowledge("node-a").knows(
        first.event_id()
    )

    assert not network.knowledge("node-a").knows(
        second.event_id()
    )

    assert network.knowledge("node-b").knows(
        second.event_id()
    )

    assert not network.knowledge("node-b").knows(
        first.event_id()
    )

    network.reconcile(
        "node-a",
        "node-b",
    )

    merged_a = network.knowledge("node-a")
    merged_b = network.knowledge("node-b")

    assert merged_a.knows(first.event_id())
    assert merged_a.knows(second.event_id())

    assert merged_b.knows(first.event_id())
    assert merged_b.knows(second.event_id())

    assert merged_a.events == merged_b.events


def test_partition_reconciliation_preserves_conflict_without_winner():
    from core.event import Transfer
    from core.partial_knowledge import PartialKnowledge
    from core.partition_conflict import find_conflicts
    from simulator.partition import NetworkPartition

    first = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    conflict = Transfer(
        "alice",
        "carol",
        4,
        0,
    )

    independent = Transfer(
        "dave",
        "eve",
        2,
        0,
    )

    network = NetworkPartition(
        nodes={
            "node-a": PartialKnowledge(
                events=frozenset({
                    first,
                    independent,
                }),
            ),
            "node-b": PartialKnowledge(
                events=frozenset({
                    conflict,
                }),
            ),
        }
    )

    # Durante la partizione i nodi hanno conoscenza diversa.
    assert network.knowledge("node-a").knows(
        first.event_id()
    )

    assert network.knowledge("node-b").knows(
        conflict.event_id()
    )

    assert not network.knowledge("node-a").knows(
        conflict.event_id()
    )

    assert not network.knowledge("node-b").knows(
        first.event_id()
    )

    # Riconciliazione.
    network.reconcile(
        "node-a",
        "node-b",
    )

    knowledge_a = network.knowledge("node-a")
    knowledge_b = network.knowledge("node-b")

    # Entrambi conoscono entrambe le alternative.
    assert knowledge_a.knows(first.event_id())
    assert knowledge_a.knows(conflict.event_id())

    assert knowledge_b.knows(first.event_id())
    assert knowledge_b.knows(conflict.event_id())

    # E anche l'evento indipendente.
    assert knowledge_a.knows(independent.event_id())
    assert knowledge_b.knows(independent.event_id())

    # Il conflitto viene rilevato dopo la riconciliazione.
    conflicts = find_conflicts(
        knowledge_a,
        knowledge_b,
    )

    assert any(
        {
            item.first.event_id(),
            item.second.event_id(),
        }
        == {
            first.event_id(),
            conflict.event_id(),
        }
        for item in conflicts
    )

    # La riconciliazione NON sceglie un vincitore:
    # entrambe le alternative restano nella conoscenza.
    assert first in knowledge_a.events
    assert conflict in knowledge_a.events
    assert first in knowledge_b.events
    assert conflict in knowledge_b.events


def test_three_node_reconciliation_is_pairwise():
    from core.event import Transfer
    from core.partial_knowledge import PartialKnowledge
    from simulator.partition import NetworkPartition

    event_a = Transfer("alice", "bob", 3, 0)
    event_b = Transfer("alice", "carol", 4, 0)
    event_c = Transfer("dave", "eve", 2, 0)
    event_d = Transfer("frank", "gina", 1, 0)

    network = NetworkPartition(
        nodes={
            "node-a": PartialKnowledge(
                events=frozenset({event_a})
            ),
            "node-b": PartialKnowledge(
                events=frozenset({event_b})
            ),
            "node-c": PartialKnowledge(
                events=frozenset({event_c, event_d})
            ),
        }
    )

    # B <-> C: solo B e C vengono sincronizzati.
    network.reconcile("node-b", "node-c")

    assert network.knowledge("node-b").events == frozenset({
        event_b,
        event_c,
        event_d,
    })

    assert network.knowledge("node-c").events == frozenset({
        event_b,
        event_c,
        event_d,
    })

    # B <-> A: A e B vengono sincronizzati.
    network.reconcile("node-b", "node-a")

    expected_all = frozenset({
        event_a,
        event_b,
        event_c,
        event_d,
    })

    assert network.knowledge("node-a").events == expected_all
    assert network.knowledge("node-b").events == expected_all

    # C non viene aggiornato automaticamente:
    # la riconciliazione è pairwise.
    assert network.knowledge("node-c").events == frozenset({
        event_b,
        event_c,
        event_d,
    })


def test_partial_knowledge_does_not_resolve_unknown_conflict():
    from core.event import Transfer
    from core.partial_knowledge import PartialKnowledge
    from core.partition_conflict import find_conflicts
    from simulator.partition import NetworkPartition

    first = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    conflict = Transfer(
        "alice",
        "carol",
        4,
        0,
    )

    network = NetworkPartition(
        nodes={
            "node-a": PartialKnowledge(
                events=frozenset({first}),
            ),
            "node-b": PartialKnowledge(
                events=frozenset({
                    first,
                    conflict,
                }),
            ),
            "node-c": PartialKnowledge(
                events=frozenset({first}),
            ),
        }
    )

    # A e C conoscono solo una delle alternative.
    assert not find_conflicts(
        network.knowledge("node-a"),
        network.knowledge("node-a"),
    )

    assert not find_conflicts(
        network.knowledge("node-c"),
        network.knowledge("node-c"),
    )

    # B conosce entrambe.
    conflicts = find_conflicts(
        network.knowledge("node-b"),
        network.knowledge("node-b"),
    )

    assert any(
        {
            item.first.event_id(),
            item.second.event_id(),
        }
        == {
            first.event_id(),
            conflict.event_id(),
        }
        for item in conflicts
    )

    # C non deve acquisire implicitamente informazioni che non possiede.
    assert not network.knowledge("node-c").knows(
        conflict.event_id()
    )

    # Riconciliazione C <-> B.
    network.reconcile(
        "node-c",
        "node-b",
    )

    # Ora C conosce entrambe le alternative.
    assert network.knowledge("node-c").knows(
        first.event_id()
    )

    assert network.knowledge("node-c").knows(
        conflict.event_id()
    )

    conflicts_after = find_conflicts(
        network.knowledge("node-c"),
        network.knowledge("node-c"),
    )

    assert any(
        {
            item.first.event_id(),
            item.second.event_id(),
        }
        == {
            first.event_id(),
            conflict.event_id(),
        }
        for item in conflicts_after
    )
