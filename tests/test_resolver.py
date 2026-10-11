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

def test_reordered_parents_are_not_a_conflict():
    parent_a = Transfer("alice", "bob", 1, 0)
    parent_b = Transfer("carol", "dave", 1, 0)

    first = Transfer(
        "eve", "frank", 1, 0,
        parents=(parent_a.event_id(), parent_b.event_id()),
    )
    reordered = Transfer(
        "eve", "frank", 1, 0,
        parents=(parent_b.event_id(), parent_a.event_id()),
    )

    assert first.event_id() == reordered.event_id()
    assert ConflictResolver.conflicting(first, reordered) is False
    assert ConflictResolver.compatible([first, reordered])
