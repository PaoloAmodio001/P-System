from core.event import Transfer


def causal_closure(events: list[Transfer]) -> set[str]:
    by_id = {
        event.event_id(): event
        for event in events
    }

    closure = set(by_id)

    changed = True

    while changed:
        changed = False

        for event in events:
            for parent in event.parents:
                if parent in by_id and parent not in closure:
                    closure.add(parent)
                    changed = True

    return closure


def test_hidden_bridge_is_not_visible_to_local_closure():
    visible = Transfer(
        sender="alice",
        receiver="bob",
        amount=3,
        nonce=0,
    )

    hidden_bridge = Transfer(
        sender="bob",
        receiver="carol",
        amount=2,
        nonce=0,
        parents=(visible.event_id(),),
    )

    hidden_descendant = Transfer(
        sender="carol",
        receiver="dave",
        amount=1,
        nonce=0,
        parents=(hidden_bridge.event_id(),),
    )

    # Il nodo conosce soltanto la regione locale.
    local_events = [visible]

    closure = causal_closure(local_events)

    assert visible.event_id() in closure

    # Il ponte e il suo discendente sono completamente
    # assenti dalla conoscenza locale.
    assert hidden_bridge.event_id() not in closure
    assert hidden_descendant.event_id() not in closure


def test_hidden_bridge_can_extend_a_known_causal_region():
    visible = Transfer(
        sender="alice",
        receiver="bob",
        amount=3,
        nonce=0,
    )

    hidden_bridge = Transfer(
        sender="bob",
        receiver="carol",
        amount=2,
        nonce=0,
        parents=(visible.event_id(),),
    )

    hidden_descendant = Transfer(
        sender="carol",
        receiver="dave",
        amount=1,
        nonce=0,
        parents=(hidden_bridge.event_id(),),
    )

    full_events = [
        visible,
        hidden_bridge,
        hidden_descendant,
    ]

    full_closure = causal_closure(full_events)

    assert visible.event_id() in full_closure
    assert hidden_bridge.event_id() in full_closure
    assert hidden_descendant.event_id() in full_closure


def test_local_closure_cannot_prove_global_closure():
    visible = Transfer(
        sender="alice",
        receiver="bob",
        amount=3,
        nonce=0,
    )

    hidden_bridge = Transfer(
        sender="bob",
        receiver="carol",
        amount=2,
        nonce=0,
        parents=(visible.event_id(),),
    )

    local = causal_closure([visible])
    full = causal_closure([visible, hidden_bridge])

    # La chiusura locale è internamente coerente.
    assert local == {visible.event_id()}

    # Ma la chiusura completa contiene informazione aggiuntiva.
    assert full == {
        visible.event_id(),
        hidden_bridge.event_id(),
    }

    # Quindi l'uguaglianza tra "closure locale" e
    # "closure globale" non può essere dedotta
    # dalla sola conoscenza locale.
    assert local != full
