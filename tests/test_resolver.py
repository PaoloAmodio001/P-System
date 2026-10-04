from core.event import Transfer
from core.resolver import ConflictResolver


def test_same_sender_same_nonce_conflicts():

    tx_a = Transfer(
        "bob",
        "carol",
        1,
        1,
    )

    tx_b = Transfer(
        "bob",
        "dave",
        1,
        1,
    )

    assert ConflictResolver.conflicting(tx_a, tx_b)
    assert not ConflictResolver.compatible([tx_a, tx_b])


def test_different_nonces_are_compatible():

    tx_a = Transfer(
        "bob",
        "carol",
        1,
        1,
    )

    tx_b = Transfer(
        "bob",
        "dave",
        1,
        2,
    )

    assert not ConflictResolver.conflicting(tx_a, tx_b)
    assert ConflictResolver.compatible([tx_a, tx_b])


def test_different_senders_are_compatible():

    tx_a = Transfer(
        "bob",
        "carol",
        1,
        1,
    )

    tx_b = Transfer(
        "alice",
        "dave",
        1,
        1,
    )

    assert not ConflictResolver.conflicting(tx_a, tx_b)
    assert ConflictResolver.compatible([tx_a, tx_b])
