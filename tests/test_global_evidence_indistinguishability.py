from dataclasses import dataclass

from core.event import Transfer
from core.partial_knowledge import PartialKnowledge


@dataclass(frozen=True)
class GlobalWorld:
    events: frozenset[Transfer]


def test_two_global_worlds_can_be_locally_indistinguishable():
    local = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    hidden = Transfer(
        "carol",
        "dave",
        2,
        0,
    )

    world_a = GlobalWorld(
        events=frozenset({
            local,
        })
    )

    world_b = GlobalWorld(
        events=frozenset({
            local,
            hidden,
        })
    )

    node_knowledge = PartialKnowledge(
        events=frozenset({
            local,
        })
    )

    assert world_a.events != world_b.events

    assert node_knowledge.events.issubset(
        world_a.events
    )

    assert node_knowledge.events.issubset(
        world_b.events
    )


def test_same_local_observation_cannot_prove_which_world_exists():
    local = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    hidden = Transfer(
        "carol",
        "dave",
        2,
        0,
    )

    world_a = frozenset({
        local,
    })

    world_b = frozenset({
        local,
        hidden,
    })

    observation_a = frozenset({
        local,
    })

    observation_b = frozenset({
        local,
    })

    assert observation_a == observation_b

    assert world_a != world_b


def test_local_completeness_cannot_distinguish_hidden_global_event():
    local = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    hidden = Transfer(
        "carol",
        "dave",
        2,
        0,
    )

    knowledge = PartialKnowledge(
        events=frozenset({
            local,
        })
    )

    world_without_hidden = frozenset({
        local,
    })

    world_with_hidden = frozenset({
        local,
        hidden,
    })

    assert knowledge.complete() is True

    assert knowledge.events.issubset(
        world_without_hidden
    )

    assert knowledge.events.issubset(
        world_with_hidden
    )
