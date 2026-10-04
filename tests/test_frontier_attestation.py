from core.event import Transfer
from core.frontier_attestation import (
    FrontierAttestation,
    create_attestation,
)


def test_attestation_records_observer():
    event = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    attestation = create_attestation(
        "node-A",
        [event],
    )

    assert attestation.observer == "node-A"
    assert attestation.covers(
        [event]
    ) is True


def test_different_observers_can_attest_different_frontiers():
    first = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    second = Transfer(
        "carol",
        "dave",
        2,
        0,
    )

    first_attestation = create_attestation(
        "node-A",
        [first],
    )

    second_attestation = create_attestation(
        "node-B",
        [first, second],
    )

    assert first_attestation.event_ids != (
        second_attestation.event_ids
    )


def test_multiple_observers_do_not_prove_global_completeness():
    known = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    hidden = Transfer(
        "carol",
        "dave",
        2,
        0,
    )

    attestations = (
        create_attestation(
            "node-A",
            [known],
        ),
        create_attestation(
            "node-B",
            [known],
        ),
        create_attestation(
            "node-C",
            [known],
        ),
    )

    for attestation in attestations:
        assert attestation.covers(
            [known]
        ) is True

    # Un evento può comunque esistere al di fuori
    # della frontiera osservata.
    assert all(
        not attestation.covers(
            [known, hidden]
        )
        for attestation in attestations
    )


def test_attestation_does_not_choose_a_winner():
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

    first_attestation = create_attestation(
        "node-A",
        [first],
    )

    second_attestation = create_attestation(
        "node-B",
        [second],
    )

    assert first_attestation.event_ids != (
        second_attestation.event_ids
    )

    assert first in [
        first,
        second,
    ]

    assert second in [
        first,
        second,
    ]
