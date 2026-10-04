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
