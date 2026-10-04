from core.event import Transfer
from core.state import State


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


def test_impact_closure_contains_causal_chain():
    a = Transfer(
        sender="alice",
        receiver="bob",
        amount=5,
        nonce=0,
    )

    b = Transfer(
        sender="bob",
        receiver="carol",
        amount=3,
        nonce=0,
        parents=(a.event_id(),),
    )

    c = Transfer(
        sender="carol",
        receiver="dave",
        amount=2,
        nonce=0,
        parents=(b.event_id(),),
    )

    closure = impact_closure([c, b, a])

    assert a.event_id() in closure
    assert b.event_id() in closure
    assert c.event_id() in closure


def test_impact_closure_excludes_unrelated_event():
    a = Transfer(
        sender="alice",
        receiver="bob",
        amount=5,
        nonce=0,
    )

    unrelated = Transfer(
        sender="x",
        receiver="y",
        amount=1,
        nonce=0,
    )

    closure = impact_closure([a])

    assert a.event_id() in closure
    assert unrelated.event_id() not in closure


def test_impact_closure_is_transitive():
    a = Transfer(
        sender="alice",
        receiver="bob",
        amount=5,
        nonce=0,
    )

    b = Transfer(
        sender="bob",
        receiver="carol",
        amount=3,
        nonce=0,
        parents=(a.event_id(),),
    )

    c = Transfer(
        sender="carol",
        receiver="dave",
        amount=2,
        nonce=0,
        parents=(b.event_id(),),
    )

    closure = impact_closure([c, b, a])

    assert closure == {
        a.event_id(),
        b.event_id(),
        c.event_id(),
    }
