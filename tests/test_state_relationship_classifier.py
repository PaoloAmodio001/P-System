from core.event import Transfer
from core.state import State
from core.state_relationship import (
    StateRelationship,
    classify_relationship,
)


def test_classifies_compatible_events():
    initial = State(
        balances={
            "alice": 10,
            "bob": 0,
            "carol": 10,
            "dave": 0,
        }
    )

    first = Transfer("alice", "bob", 3, 0)
    second = Transfer("carol", "dave", 2, 0)

    assert classify_relationship(
        initial,
        first,
        second,
    ) == StateRelationship.COMPATIBLE


def test_classifies_order_dependent_events():
    initial = State(
        balances={
            "alice": 5,
            "bob": 0,
            "carol": 0,
        }
    )

    first = Transfer("alice", "bob", 5, 0)
    second = Transfer("bob", "carol", 5, 0)

    assert classify_relationship(
        initial,
        first,
        second,
    ) == StateRelationship.ORDER_DEPENDENT


def test_classifies_absolute_conflict():
    initial = State(
        balances={
            "alice": 5,
            "bob": 0,
            "carol": 0,
        }
    )

    first = Transfer("alice", "bob", 5, 0)
    second = Transfer("alice", "carol", 4, 1)

    assert classify_relationship(
        initial,
        first,
        second,
    ) == StateRelationship.CONFLICT
