from core.event import Transfer
from core.global_domain import build_global_domain
from core.global_frontier import build_frontier
from core.partial_knowledge import PartialKnowledge


def test_global_domain_and_frontier_do_not_prove_absence_of_relevant_event():
    visible = Transfer(
        "alice",
        "bob",
        5,
        0,
    )

    hidden = Transfer(
        "alice",
        "carol",
        5,
        0,
    )

    knowledge = PartialKnowledge(
        events=frozenset({visible})
    )

    domain = build_global_domain(
        [visible]
    )

    frontier = build_frontier(
        [visible]
    )

    # Everything known locally is covered.
    assert knowledge.complete()
    assert domain.covers([visible])
    assert frontier.covers([visible])

    # But neither structure proves that a relevant concurrent
    # event cannot exist outside the known set.
    assert not domain.covers([visible, hidden])
    assert not frontier.covers([visible, hidden])

    # Therefore the hidden event remains a valid counterexample
    # to any claim of global completeness based only on these
    # structures.
    assert hidden.event_id() not in knowledge.event_ids()
    assert hidden.event_id() not in domain.event_ids
    assert hidden.event_id() not in frontier.event_ids
