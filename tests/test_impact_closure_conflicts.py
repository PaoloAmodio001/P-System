from core.event import Transfer


def impact_closure(events: list[Transfer]) -> set[str]:
    by_id = {
        event.event_id(): event
        for event in events
    }

    impacted = set(by_id)

    changed = True

    while changed:
        changed = False

        for event in events:
            event_id = event.event_id()

            if event_id in impacted:
                for parent in event.parents:
                    if parent in by_id and parent not in impacted:
                        impacted.add(parent)
                        changed = True

    return impacted


def find_conflicts(events: list[Transfer]):
    conflicts = []

    for i, first in enumerate(events):
        for second in events[i + 1:]:
            if (
                first.sender == second.sender
                and first.nonce == second.nonce
                and first != second
            ):
                conflicts.append(
                    (first.event_id(), second.event_id())
                )

    return conflicts


def test_conflicting_alternative_is_part_of_impact_domain():
    visible = Transfer(
        sender="alice",
        receiver="bob",
        amount=3,
        nonce=0,
    )

    alternative = Transfer(
        sender="alice",
        receiver="carol",
        amount=5,
        nonce=0,
    )

    events = [visible, alternative]

    conflicts = find_conflicts(events)

    assert conflicts == [
        (visible.event_id(), alternative.event_id())
    ]

    # La closure causale da sola non cattura l'alternativa.
    closure = impact_closure([visible])

    assert alternative.event_id() not in closure


def test_conflict_must_expand_impact_closure():
    visible = Transfer(
        sender="alice",
        receiver="bob",
        amount=3,
        nonce=0,
    )

    alternative = Transfer(
        sender="alice",
        receiver="carol",
        amount=5,
        nonce=0,
    )

    child = Transfer(
        sender="carol",
        receiver="dave",
        amount=2,
        nonce=0,
        parents=(alternative.event_id(),),
    )

    events = [
        visible,
        alternative,
        child,
    ]

    conflicts = find_conflicts(events)

    assert len(conflicts) == 1

    conflicting_ids = {
        event_id
        for pair in conflicts
        for event_id in pair
    }

    assert visible.event_id() in conflicting_ids
    assert alternative.event_id() in conflicting_ids

    # La catena alternativa deve essere riconosciuta
    # come potenzialmente rilevante.
    closure = impact_closure(
        [alternative, child]
    )

    assert alternative.event_id() in closure
    assert child.event_id() in closure


def test_conflict_and_causal_chain_form_one_relevance_region():
    visible = Transfer(
        sender="alice",
        receiver="bob",
        amount=3,
        nonce=0,
    )

    alternative = Transfer(
        sender="alice",
        receiver="carol",
        amount=5,
        nonce=0,
    )

    child = Transfer(
        sender="carol",
        receiver="dave",
        amount=2,
        nonce=0,
        parents=(alternative.event_id(),),
    )

    events = [
        visible,
        alternative,
        child,
    ]

    conflicts = find_conflicts(events)

    assert conflicts

    conflict_ids = {
        event_id
        for pair in conflicts
        for event_id in pair
    }

    assert visible.event_id() in conflict_ids
    assert alternative.event_id() in conflict_ids

    causal_closure = impact_closure(
        [alternative, child]
    )

    combined_region = (
        causal_closure
        | conflict_ids
    )

    assert visible.event_id() in combined_region
    assert alternative.event_id() in combined_region
    assert child.event_id() in combined_region
