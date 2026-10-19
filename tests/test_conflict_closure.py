from core.conflict_closure import (
    build_conflict_closure,
    find_conflicts,
)
from core.event import Transfer


def test_no_conflicts():
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

    assert find_conflicts(
        [first, second]
    ) == ()


def test_conflicting_same_nonce_is_detected():
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

    conflicts = find_conflicts(
        [first, second]
    )

    assert len(conflicts) == 1
    assert set(conflicts[0]) == {
        first.event_id(),
        second.event_id(),
    }


def test_different_nonces_are_not_conflicts():
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
        1,
    )

    assert find_conflicts(
        [first, second]
    ) == ()


def test_closure_contains_all_events():
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

    closure = build_conflict_closure(
        [first, second]
    )

    assert closure.contains(
        first.event_id()
    )

    assert closure.contains(
        second.event_id()
    )


def test_conflict_closure_preserves_conflict_without_winner():
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

    closure = build_conflict_closure(
        [first, second]
    )

    assert closure.has_conflicts()
    assert len(closure.conflicts) == 1


def test_conflict_closure_does_not_choose_winner():
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

    closure = build_conflict_closure(
        [first, second]
    )

    assert first.event_id() in closure.event_ids
    assert second.event_id() in closure.event_ids
    assert len(closure.conflicts) == 1

def test_conflict_scan_rejects_same_id_with_different_payload():
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
        find_conflicts([first, second])
    except ValueError as exc:
        assert str(exc) == "DUPLICATE EVENT ID WITH DIFFERENT CONTENT"
    else:
        raise AssertionError("La scansione dei conflitti ha accettato ID ambiguo")
