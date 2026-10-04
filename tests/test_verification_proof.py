from core.event import Transfer
from core.verification_proof import VerificationProof


def test_verification_proof_is_created():
    event = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    proof = VerificationProof.create(
        [event]
    )

    assert proof.event_ids == frozenset({
        event.event_id()
    })

    assert proof.conflict_count == 0


def test_valid_proof_verifies():
    event = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    proof = VerificationProof.create(
        [event]
    )

    assert proof.verify(
        [event]
    ) is True


def test_modified_events_fail_verification():
    event = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    proof = VerificationProof.create(
        [event]
    )

    modified = Transfer(
        "alice",
        "carol",
        3,
        0,
    )

    assert proof.verify(
        [modified]
    ) is False


def test_missing_parent_fails_verification():
    parent = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    child = Transfer(
        "bob",
        "carol",
        2,
        0,
        parents=(parent.event_id(),),
    )

    proof = VerificationProof(
        event_ids=frozenset({
            child.event_id()
        }),
        conflict_count=0,
    )

    assert proof.verify(
        [child]
    ) is False


def test_conflict_count_is_verified():
    first = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    second = Transfer(
        "alice",
        "carol",
        4,
        0,
    )

    proof = VerificationProof.create(
        [first, second]
    )

    assert proof.conflict_count == 1
    assert proof.verify(
        [first, second]
    ) is True


def test_tampered_conflict_count_fails():
    first = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    second = Transfer(
        "alice",
        "carol",
        4,
        0,
    )

    proof = VerificationProof(
        event_ids=frozenset({
            first.event_id(),
            second.event_id(),
        }),
        conflict_count=0,
    )

    assert proof.verify(
        [first, second]
    ) is False
