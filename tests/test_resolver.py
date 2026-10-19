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


def test_resolver_rejects_same_id_with_different_payload():
    class ForcedIdEvent:
        def __init__(self, amount):
            self.sender = "alice"
            self.receiver = "bob"
            self.amount = amount
            self.nonce = 0
            self.parents = ()

        def event_id(self):
            return "a" * 64

        def canonical(self):
            return str(self.amount).encode()

    first = ForcedIdEvent(3)
    second = ForcedIdEvent(4)

    try:
        ConflictResolver.conflicting(first, second)
    except ValueError as exc:
        assert str(exc) == "DUPLICATE EVENT ID WITH DIFFERENT CONTENT"
    else:
        raise AssertionError("ID identico con payload diverso accettato")

    try:
        ConflictResolver.compatible([first, second])
    except ValueError as exc:
        assert str(exc) == "DUPLICATE EVENT ID WITH DIFFERENT CONTENT"
    else:
        raise AssertionError("La compatibilità ha accettato ID duplicati incoerenti")


def test_resolver_accepts_identical_payload_with_same_id():
    class ForcedIdEvent:
        def __init__(self):
            self.sender = "alice"
            self.receiver = "bob"
            self.amount = 3
            self.nonce = 0
            self.parents = ()

        def event_id(self):
            return "a" * 64

        def canonical(self):
            return b"identical-payload"

    first = ForcedIdEvent()
    second = ForcedIdEvent()

    assert not ConflictResolver.conflicting(first, second)
    assert ConflictResolver.compatible([first, second])
