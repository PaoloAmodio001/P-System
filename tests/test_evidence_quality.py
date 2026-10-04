from core.event import Transfer
from core.evidence import Evidence
from core.evidence_quality import (
    independent_observers,
    has_independent_observation,
)
from core.signed_event import SignedTransfer
from crypto.identity import Identity


def test_duplicate_observer_does_not_increase_independence():
    identity = Identity.create()

    event = Transfer(
        sender="alice",
        receiver="bob",
        amount=5,
        nonce=0,
    )

    signed = SignedTransfer.create(
        identity,
        event,
    )

    evidence = Evidence(
        event=signed,
        observed_by=frozenset({
            "node-1",
            "node-1",
            "node-2",
        }),
    )

    assert independent_observers(evidence) == {
        "node-1",
        "node-2",
    }

    assert has_independent_observation(evidence, 2)
    assert not has_independent_observation(evidence, 3)


def test_independent_observers_are_counted_once():
    identity = Identity.create()

    event = Transfer(
        sender="alice",
        receiver="bob",
        amount=5,
        nonce=0,
    )

    signed = SignedTransfer.create(
        identity,
        event,
    )

    evidence = Evidence(
        event=signed,
        observed_by=frozenset({
            "node-1",
            "node-2",
            "node-3",
        }),
    )

    assert len(independent_observers(evidence)) == 3
    assert has_independent_observation(evidence, 3)


def test_empty_evidence_has_no_independent_observers():
    identity = Identity.create()

    event = Transfer(
        sender="alice",
        receiver="bob",
        amount=5,
        nonce=0,
    )

    signed = SignedTransfer.create(
        identity,
        event,
    )

    evidence = Evidence(
        event=signed,
        observed_by=frozenset(),
    )

    assert independent_observers(evidence) == frozenset()
    assert not has_independent_observation(evidence, 1)
