from core.event import Transfer
from core.precedence import PrecedenceAttestation
from core.precedence_conflict import contradictory
from crypto.identity import Identity


def test_contradictory_precedence_is_detectable():
    identity_a = Identity.create()
    identity_b = Identity.create()

    event_a = Transfer(
        sender="alice",
        receiver="bob",
        amount=5,
        nonce=0,
    )

    event_b = Transfer(
        sender="carol",
        receiver="dave",
        amount=3,
        nonce=0,
    )

    first = PrecedenceAttestation.create(
        identity=identity_a,
        earlier_event=event_a.event_id(),
        later_event=event_b.event_id(),
    )

    second = PrecedenceAttestation.create(
        identity=identity_b,
        earlier_event=event_b.event_id(),
        later_event=event_a.event_id(),
    )

    assert first.verify()
    assert second.verify()

    assert contradictory(first, second)


def test_non_contradictory_precedence_is_compatible():
    identity = Identity.create()

    event_a = Transfer(
        sender="alice",
        receiver="bob",
        amount=5,
        nonce=0,
    )

    event_b = Transfer(
        sender="bob",
        receiver="carol",
        amount=3,
        nonce=0,
    )

    event_c = Transfer(
        sender="carol",
        receiver="dave",
        amount=2,
        nonce=0,
    )

    first = PrecedenceAttestation.create(
        identity=identity,
        earlier_event=event_a.event_id(),
        later_event=event_b.event_id(),
    )

    second = PrecedenceAttestation.create(
        identity=identity,
        earlier_event=event_b.event_id(),
        later_event=event_c.event_id(),
    )

    assert first.verify()
    assert second.verify()

    assert not contradictory(first, second)
