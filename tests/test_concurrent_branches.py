from core.event import Transfer
from core.causality import CausalGraph


def test_concurrent_branches():

    graph = CausalGraph()

    # Common origin
    event_a = Transfer(
        "alice",
        "bob",
        1,
        0,
    )

    id_a = graph.add(event_a)

    # Two concurrent branches
    event_b = Transfer(
        "bob",
        "carol",
        1,
        0,
        parents=(id_a,),
    )

    event_c = Transfer(
        "bob",
        "dave",
        1,
        0,
        parents=(id_a,),
    )

    id_b = graph.add(event_b)
    id_c = graph.add(event_c)

    # Both branches are causally valid.
    assert graph.contains(id_b)
    assert graph.contains(id_c)

    assert graph.ancestors(id_b) == {id_a}
    assert graph.ancestors(id_c) == {id_a}

    # They are concurrent:
    # neither event depends on the other.
    assert id_c not in graph.ancestors(id_b)
    assert id_b not in graph.ancestors(id_c)

    assert id_b != id_c
