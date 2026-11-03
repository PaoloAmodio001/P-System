"""
Regression tests: valid histories whose dependencies are implicit
(not declared through `parents`) must be accepted regardless of the
hash values of their event ids, and the derived state must depend
only on the event set.
"""

import random

import pytest

from core.derive import StateDeriver
from core.event import Transfer
from core.state import State


ROUNDS = 60


def test_unlinked_consecutive_nonces_are_accepted():
    initial = State(balances={"alice": 10})

    for r in range(ROUNDS):
        first = Transfer("alice", f"r{r}", 1, 0)
        second = Transfer("alice", f"q{r}", 1, 1)

        state = StateDeriver.apply_events(initial, [first, second])

        assert state.balance("alice") == 8
        assert state.nonce("alice") == 2


def test_unlinked_receive_then_spend_is_accepted():
    initial = State(balances={"alice": 10})

    for r in range(ROUNDS):
        receive = Transfer("alice", f"c{r}", 10, 0)
        spend = Transfer(f"c{r}", "dave", 5, 0)

        state = StateDeriver.apply_events(initial, [receive, spend])

        assert state.balance(f"c{r}") == 5
        assert state.balance("dave") == 5


def test_derived_state_is_independent_of_input_order():
    initial = State(balances={"alice": 10, "bob": 3})
    events = [
        Transfer("alice", "bob", 4, 0),
        Transfer("alice", "carol", 2, 1),
        Transfer("bob", "carol", 7, 0),
        Transfer("carol", "dave", 9, 0),
    ]
    expected = StateDeriver.apply_events(initial, events).root()

    rng = random.Random(0)
    for _ in range(ROUNDS):
        shuffled = events[:]
        rng.shuffle(shuffled)
        assert StateDeriver.apply_events(initial, shuffled).root() == expected


def test_nonce_gap_is_still_rejected():
    initial = State(balances={"alice": 10})
    events = [
        Transfer("alice", "bob", 1, 0),
        Transfer("alice", "bob", 1, 2),
    ]

    with pytest.raises(ValueError, match="INVALID NONCE"):
        StateDeriver.apply_events(initial, events)


def test_insufficient_total_funds_are_still_rejected():
    initial = State(balances={"alice": 5})
    events = [
        Transfer("alice", "bob", 4, 0),
        Transfer("alice", "carol", 4, 1),
    ]

    with pytest.raises(ValueError, match="INSUFFICIENT BALANCE"):
        StateDeriver.apply_events(initial, events)


def test_spending_funds_that_never_arrive_is_rejected():
    initial = State(balances={"alice": 10})
    events = [Transfer("carol", "dave", 5, 0)]

    with pytest.raises(ValueError, match="INSUFFICIENT BALANCE"):
        StateDeriver.apply_events(initial, events)
