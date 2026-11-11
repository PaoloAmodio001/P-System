"""Changing committee on real TLS, under traffic, with a faulty member.

The properties of no_double_spend_across_epochs and state_is_derive, checked on each run.
EMPIRICAL, for n = 4, f = 1, on these scenarios. A faulty member can only refuse to take part
here; the attacks on messages are in tests/test_quorum_differential_network.py and
tests/test_quorum_epochs.py. A closure that never forms is a possible outcome and these
tests do not show otherwise: they show that one forms when the network and a quorum work.
"""

import threading
import time

import pytest

from core.attestation import Committee, EpochChange, Governance
from core.derive import StateDeriver
from core.event import Transfer
from core.signed_event import SignedTransfer
from core.state import State
from crypto.identity import Identity
from network.node import Node
from network.peer import Peer
from network.quorum import QuorumConfig

SENDERS = [Identity.create() for _ in range(2)]
GENESIS = State({sender.identity_id: 10_000 for sender in SENDERS})
SIGNERS = [Identity.create() for _ in range(3)]
GOVERNANCE = Governance(tuple(sorted(s.public_key for s in SIGNERS)), 2)
OLD = sorted((Identity.create() for _ in range(4)), key=lambda m: m.public_key)
ADDED = Identity.create()
COMMITTEE = Committee.create([m.public_key for m in OLD], 1, GENESIS)


def wait_until(condition, seconds: float = 25.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return condition()


def spend(sender: Identity, nonce: int, receiver: str = "bob") -> SignedTransfer:
    return SignedTransfer.create(
        sender,
        Transfer(sender.identity_id, receiver, 1, nonce),
    )


@pytest.fixture
def make_node(tmp_path):
    made = []

    def make(member: Identity, name: str, joining: bool = False) -> Node:
        node = Node(
            f"{name}-{tmp_path.name[-10:].replace('_', '-')}",
            GENESIS,
            quorum=QuorumConfig(
                COMMITTEE,
                member,
                tmp_path / f"{name}.sqlite",
                create=True,
                sync_interval=0.2,
                governance=GOVERNANCE,
                joining=joining,
            ),
        )
        node.start()
        made.append(node)
        return node

    yield make

    for node in made:
        node.stop()


def link(*nodes) -> None:
    for index, low in enumerate(nodes):
        for high in nodes[index + 1:]:
            host, port = high.address()
            assert low.connect_peer(Peer(node_id=high.node_id, host=host, port=port))

    assert wait_until(
        lambda: all(len(node.peer_connections) >= len(nodes) - 1 for node in nodes)
    )


def assert_safe(nodes) -> None:
    seen = {}
    for node in nodes:
        for event in node.local_events:
            first = seen.setdefault((event.sender, event.nonce), event)
            assert first.canonical() == event.canonical()
        # Under the lock: see tests/test_quorum_differential_network.py.
        with node._state_lock:
            events = list(node.local_events)
            root = node.state.root()

        assert root == StateDeriver.apply_events(GENESIS.copy(), events).root()
        assert not node.conflicted


def change(current: Committee, keys) -> EpochChange:
    return EpochChange.create(current, keys, 1, GOVERNANCE, SIGNERS[:2])


@pytest.mark.filterwarnings("error::pytest.PytestUnhandledThreadExceptionWarning")
def test_a_member_replaced_with_a_silent_old_member(make_node):
    # Three of the four old members work: the fourth never starts. A new member takes its
    # place, catches up from the others, and takes part in certifying.
    nodes = [make_node(OLD[i], f"old{i}") for i in range(3)]
    link(*nodes)
    first = spend(SENDERS[0], 0)
    assert nodes[0].submit(first)
    assert wait_until(lambda: all(n.local_events == [first.transfer] for n in nodes))

    keys = [OLD[i].public_key for i in range(3)] + [ADDED.public_key]
    assert nodes[1].propose_epoch_change(change(COMMITTEE, keys))
    assert wait_until(lambda: all(n.committee_epoch == 1 for n in nodes))

    added = make_node(ADDED, "added", joining=True)
    assert added.committee_epoch == 0
    link(*nodes, added)
    assert wait_until(lambda: added.committee_epoch == 1)
    assert wait_until(lambda: added.local_events == [first.transfer])

    # The alternative of an old event gets nothing from anyone.
    assert not added.submit(spend(SENDERS[0], 0, "carol"))
    assert not nodes[0].submit(spend(SENDERS[0], 0, "carol"))

    # With one old member stopped, the new one is needed for the quorum: 2 old and 1 new.
    nodes[2].stop()
    second = spend(SENDERS[0], 1)
    assert added.submit(second)
    assert wait_until(lambda: second.transfer in added.local_events)
    assert wait_until(lambda: second.transfer in nodes[0].local_events)
    assert_safe([nodes[0], nodes[1], added])


@pytest.mark.filterwarnings("error::pytest.PytestUnhandledThreadExceptionWarning")
def test_changing_committee_under_traffic(make_node):
    nodes = [make_node(OLD[i], f"tr{i}") for i in range(4)]
    link(*nodes)
    keys = [member.public_key for member in OLD]
    stop = threading.Event()
    submitted: dict[str, list] = {sender.identity_id: [] for sender in SENDERS}

    def traffic(sender: Identity, node: Node) -> None:
        nonce = 0
        while not stop.is_set():
            signed = spend(sender, nonce)
            node.submit(signed)
            submitted[sender.identity_id].append(signed)
            nonce += 1
            time.sleep(0.01)

    threads = [
        threading.Thread(target=traffic, args=(SENDERS[0], nodes[0]), daemon=True),
        threading.Thread(target=traffic, args=(SENDERS[1], nodes[1]), daemon=True),
    ]
    for thread in threads:
        thread.start()

    time.sleep(0.5)
    assert nodes[2].propose_epoch_change(change(COMMITTEE, keys))
    assert wait_until(lambda: all(n.committee_epoch == 1 for n in nodes))
    time.sleep(0.5)
    stop.set()
    for thread in threads:
        thread.join(timeout=5)

    # The end of an epoch may leave events without a certificate. They finish when sent
    # again, because each has at most one alternative: its own.
    def resend() -> None:
        for sender in SENDERS:
            for signed in submitted[sender.identity_id]:
                if signed.transfer not in nodes[0].local_events:
                    nodes[0].submit(signed)

    def all_done() -> bool:
        return all(
            len(node.local_events) == sum(len(v) for v in submitted.values())
            for node in nodes
        )

    deadline = time.monotonic() + 40
    while not all_done() and time.monotonic() < deadline:
        resend()
        time.sleep(0.3)

    assert all_done()
    assert len({node.state.root() for node in nodes}) == 1
    assert_safe(nodes)


@pytest.mark.filterwarnings("error::pytest.PytestUnhandledThreadExceptionWarning")
def test_a_restarted_node_finds_the_epoch_it_missed(make_node, tmp_path):
    nodes = [make_node(OLD[i], f"re{i}") for i in range(4)]
    link(*nodes)
    nodes[3].stop()
    keys = [member.public_key for member in OLD]
    assert nodes[0].propose_epoch_change(change(COMMITTEE, keys))
    assert wait_until(lambda: all(n.committee_epoch == 1 for n in nodes[:3]))
    event = spend(SENDERS[0], 0)
    assert nodes[0].submit(event)
    assert wait_until(lambda: all(n.local_events == [event.transfer] for n in nodes[:3]))

    back = Node(
        "re3-again",
        GENESIS,
        quorum=QuorumConfig(
            COMMITTEE,
            OLD[3],
            tmp_path / "re3.sqlite",
            sync_interval=0.2,
            governance=GOVERNANCE,
        ),
    )
    back.start()
    try:
        host, port = nodes[0].address()
        assert back.connect_peer(Peer(node_id=nodes[0].node_id, host=host, port=port))
        assert wait_until(lambda: back.committee_epoch == 1)
        assert wait_until(lambda: back.local_events == [event.transfer])
        assert_safe([*nodes[:3], back])
    finally:
        back.stop()
