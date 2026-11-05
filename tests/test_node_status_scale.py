"""A question about the status of a node must not cost more as its log grows.

`/v1/status` took 32 seconds with 2000 events, holding the lock of the node, because it compared
every pair of events. A campaign of faults found it, once a campaign lasted long enough to have
a thousand events: nodes stopped answering, and no test with few events could see this.
"""

import random
import time

import pytest

from core.conflict_state import ConflictState
from core.event import Transfer
from core.resolver import ConflictResolver
from network.node import Node


class ForcedId(Transfer):
    def event_id(self) -> str:
        return "f" * 64


def pairwise(known) -> ConflictState:
    """The definition: every pair, with the resolver."""
    conflict = ConflictState(tuple())
    for index, first in enumerate(known):
        for second in known[index + 1:]:
            if ConflictResolver.conflicting(first, second):
                conflict = conflict.add(first)
                conflict = conflict.add(second)
    return conflict


def node_with(events) -> Node:
    node = Node("scale")
    node.events = list(events)
    return node


@pytest.mark.parametrize("seed", range(30))
def test_it_finds_what_every_pair_finds(seed):
    rng = random.Random(seed)
    events = [
        Transfer(
            rng.choice("ab"),
            rng.choice("xyz"),
            rng.randint(1, 2),
            rng.randint(0, 3),
        )
        for _ in range(rng.randint(0, 25))
    ]
    assert node_with(events)._knowledge_conflict_state() == pairwise(events)


def test_it_finds_a_conflict():
    first, second = Transfer("a", "x", 1, 0), Transfer("a", "y", 1, 0)
    other = Transfer("a", "y", 1, 1)
    found = node_with([first, other, second])._knowledge_conflict_state()
    assert found.contains(first) and found.contains(second) and not found.contains(other)


def test_the_same_event_twice_is_no_conflict():
    event = Transfer("a", "x", 1, 0)
    assert not node_with([event, event])._knowledge_conflict_state().is_conflicted()


def test_another_sender_or_nonce_is_no_conflict():
    events = [Transfer("a", "x", 1, 0), Transfer("b", "x", 1, 0), Transfer("a", "x", 1, 1)]
    assert not node_with(events)._knowledge_conflict_state().is_conflicted()


def test_one_id_with_different_content_is_an_error_as_before():
    first = ForcedId("a", "x", 1, 0)
    second = ForcedId("b", "y", 2, 1)
    with pytest.raises(ValueError, match="DUPLICATE EVENT ID"):
        pairwise([first, second])
    with pytest.raises(ValueError, match="DUPLICATE EVENT ID"):
        node_with([first, second])._knowledge_conflict_state()


def test_the_cost_does_not_grow_with_the_square_of_the_events():
    # The whole status, as the API asks it. It took 32 seconds at 2000 events, so about 3200
    # seconds at 20 000. The bound is far above what it costs now and far below that.
    events = [Transfer("a", "x", 1, nonce) for nonce in range(20_000)]
    node = node_with(events)
    started = time.monotonic()
    node.status()
    assert time.monotonic() - started < 60
