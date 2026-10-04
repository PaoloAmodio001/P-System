from core.event import Transfer
from core.partial_knowledge import PartialKnowledge


def test_hidden_concurrent_branch_is_invisible_locally():
    root = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    visible = Transfer(
        "bob",
        "carol",
        2,
        0,
        parents=(root.event_id(),),
    )

    hidden = Transfer(
        "dave",
        "erin",
        1,
        0,
    )

    # Mondo A: esistono solo root + visible.
    world_a = frozenset({
        root,
        visible,
    })

    # Mondo B: esiste anche un ramo concorrente
    # completamente indipendente.
    world_b = frozenset({
        root,
        visible,
        hidden,
    })

    knowledge = PartialKnowledge(
        events=frozenset({
            root,
            visible,
        })
    )

    # La conoscenza locale è completa dal punto
    # di vista dei parent.
    assert knowledge.complete() is True

    # Ma la stessa conoscenza è compatibile
    # con entrambi i mondi globali.
    assert knowledge.events.issubset(world_a)
    assert knowledge.events.issubset(world_b)

    assert world_a != world_b


def test_causal_frontier_cannot_detect_unknown_concurrent_branch():
    root = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    visible = Transfer(
        "bob",
        "carol",
        2,
        0,
        parents=(root.event_id(),),
    )

    hidden = Transfer(
        "dave",
        "erin",
        1,
        0,
    )

    knowledge_without_hidden = frozenset({
        root.event_id(),
        visible.event_id(),
    })

    knowledge_with_hidden = frozenset({
        root.event_id(),
        visible.event_id(),
        hidden.event_id(),
    })

    # La frontiera osservata dal nodo è la stessa
    # indipendentemente dall'esistenza del ramo nascosto.
    local_frontier = frozenset({
        root.event_id(),
        visible.event_id(),
    })

    assert local_frontier == knowledge_without_hidden

    assert local_frontier != knowledge_with_hidden
