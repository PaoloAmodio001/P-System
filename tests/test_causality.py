from core.event import Transfer
from core.causality import CausalGraph


def test_event_causality():

    graph = CausalGraph()

    event_a = Transfer(
        "alice",
        "bob",
        2,
        0,
    )

    id_a = graph.add(event_a)

    event_b = Transfer(
        "bob",
        "carol",
        1,
        0,
        parents=(id_a,),
    )

    id_b = graph.add(event_b)

    assert graph.contains(id_a)
    assert graph.contains(id_b)

    assert graph.parents_of(id_b) == (id_a,)

    assert id_a in graph.ancestors(id_b)


def test_unknown_parent_rejected():

    graph = CausalGraph()

    event = Transfer(
        "alice",
        "bob",
        1,
        0,
        parents=("does-not-exist",),
    )

    try:
        graph.add(event)
        assert False
    except ValueError:
        pass
