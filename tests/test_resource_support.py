from core.event import Transfer
from core.resource_support import (
    ResourceSupport,
    transfer_resource_support,
)


def test_transfer_resource_support_contains_complete_state_resources():
    event = Transfer(
        sender="alice",
        receiver="bob",
        amount=10,
        nonce=0,
    )

    support = transfer_resource_support(event)

    assert isinstance(support, ResourceSupport)
    assert support.resources == frozenset(
        {
            "balance:alice",
            "balance:bob",
            "nonce:alice",
        }
    )


def test_disjoint_transfer_supports():
    first = Transfer("alice", "bob", 10, 0)
    second = Transfer("carol", "dave", 20, 0)

    first_support = transfer_resource_support(first)
    second_support = transfer_resource_support(second)

    assert first_support.disjoint(second_support)
    assert not first_support.overlaps(second_support)


def test_overlapping_transfer_supports():
    first = Transfer("alice", "bob", 10, 0)
    second = Transfer("alice", "carol", 5, 1)

    first_support = transfer_resource_support(first)
    second_support = transfer_resource_support(second)

    assert first_support.overlaps(second_support)
    assert not first_support.disjoint(second_support)


def test_resource_support_membership_and_size():
    event = Transfer(
        sender="alice",
        receiver="bob",
        amount=10,
        nonce=0,
    )

    support = transfer_resource_support(event)

    assert "balance:alice" in support
    assert "balance:bob" in support
    assert "nonce:alice" in support
    assert "balance:carol" not in support
    assert len(support) == 3
