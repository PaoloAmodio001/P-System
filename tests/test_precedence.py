from core.event import Transfer
from core.precedence import PrecedenceAttestation
from crypto.identity import Identity


def test_precedence_attestation_is_verifiable():
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
        parents=(event_a.event_id(),),
    )

    attestation = PrecedenceAttestation.create(
        identity=identity,
        earlier_event=event_a.event_id(),
        later_event=event_b.event_id(),
    )

    assert attestation.verify()


def test_precedence_tampering_is_rejected():
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

    attestation = PrecedenceAttestation.create(
        identity=identity,
        earlier_event=event_a.event_id(),
        later_event=event_b.event_id(),
    )

    tampered = PrecedenceAttestation(
        earlier_event=event_a.event_id(),
        later_event=event_c.event_id(),
        observer=attestation.observer,
        signature=attestation.signature,
    )

    assert not tampered.verify()


def test_same_event_cannot_have_precedence_over_itself():
    identity = Identity.create()

    event = Transfer(
        sender="alice",
        receiver="bob",
        amount=5,
        nonce=0,
    )

    try:
        PrecedenceAttestation.create(
            identity=identity,
            earlier_event=event.event_id(),
            later_event=event.event_id(),
        )
    except ValueError:
        pass
    else:
        raise AssertionError("SELF-PRECEDENCE ACCEPTED")
