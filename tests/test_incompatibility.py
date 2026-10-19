from core.event import Transfer
from core.incompatibility import incompatible


def test_same_sender_same_nonce_is_incompatible():
    a = Transfer(
        sender="alice",
        receiver="bob",
        amount=8,
        nonce=0,
    )

    b = Transfer(
        sender="alice",
        receiver="carol",
        amount=8,
        nonce=0,
    )

    assert incompatible(a, b)


def test_different_nonce_is_compatible():
    a = Transfer(
        sender="alice",
        receiver="bob",
        amount=8,
        nonce=0,
    )

    b = Transfer(
        sender="alice",
        receiver="carol",
        amount=8,
        nonce=1,
    )

    assert not incompatible(a, b)


def test_different_sender_is_compatible():
    a = Transfer(
        sender="alice",
        receiver="bob",
        amount=8,
        nonce=0,
    )

    b = Transfer(
        sender="carol",
        receiver="dave",
        amount=8,
        nonce=0,
    )

    assert not incompatible(a, b)


def test_identical_events_are_not_incompatible():
    a = Transfer(
        sender="alice",
        receiver="bob",
        amount=8,
        nonce=0,
    )

    b = Transfer(
        sender="alice",
        receiver="bob",
        amount=8,
        nonce=0,
    )

    assert not incompatible(a, b)


def test_different_amount_same_nonce_is_incompatible():
    a = Transfer(
        sender="alice",
        receiver="bob",
        amount=8,
        nonce=0,
    )

    b = Transfer(
        sender="alice",
        receiver="bob",
        amount=5,
        nonce=0,
    )

    assert incompatible(a, b)

def test_reordered_parents_are_not_incompatible():
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
    assert not incompatible(first, reordered)

def test_same_id_with_different_payload_is_rejected():
    class ForcedIdEvent:
        def __init__(self, receiver, amount):
            self.sender = "alice"
            self.receiver = receiver
            self.amount = amount
            self.nonce = 0
            self.parents = ()

        def event_id(self):
            return "a" * 64

        def canonical(self):
            return (
                f"{self.sender}|{self.receiver}|{self.amount}|"
                f"{self.nonce}|{self.parents}"
            ).encode()

    first = ForcedIdEvent("bob", 3)
    second = ForcedIdEvent("carol", 4)

    try:
        incompatible(first, second)
    except ValueError as exc:
        assert str(exc) == "DUPLICATE EVENT ID WITH DIFFERENT CONTENT"
    else:
        raise AssertionError("ID duplicato con contenuto differente accettato")
