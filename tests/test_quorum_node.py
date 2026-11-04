"""Node in quorum mode: how the rules of network/quorum.py meet the network.

The rules themselves are tested in test_quorum_driver.py. With quorum=None the node
must not change at all, and for that the proof is that the existing tests of Node
pass unmodified.
"""

import threading
from pathlib import Path

import pytest

from core.attestation import Committee, QuorumCertificate, Vote
from core.derive import StateDeriver
from core.event import Transfer
from core.signed_event import SignedTransfer
from core.state import State
from crypto.identity import Identity
from network.message import encode_certificate, encode_vote_request
from network.node import Node
from network.quorum import QuorumConfig, VoteStoreError

SENDER = Identity.create()
PAYER = SENDER.identity_id
GENESIS = State({PAYER: 10})
A = Transfer(PAYER, "bob", 8, 0)
B = Transfer(PAYER, "carol", 8, 0)
NEXT = Transfer(PAYER, "bob", 1, 1, (A.event_id(),))


def signed(event: Transfer) -> SignedTransfer:
    return SignedTransfer.create(SENDER, event)


class Committee4:
    """Real keys for n = 4, f = 1, and files for each member."""

    def __init__(self, directory: Path):
        self.directory = directory
        self.members = sorted(
            (Identity.create() for _ in range(4)),
            key=lambda identity: identity.public_key,
        )
        self.committee = Committee.create(
            [member.public_key for member in self.members],
            1,
            GENESIS,
        )
        self.created = set()
        self.nodes = []

    def config(self, index: int = 0) -> QuorumConfig:
        create = index not in self.created
        self.created.add(index)
        return QuorumConfig(
            self.committee,
            self.members[index],
            self.directory / f"votes-{index}.sqlite",
            create=create,
        )

    def node(self, index: int = 0, name: str | None = None) -> Node:
        node = Node(name or f"q-{index}", GENESIS, quorum=self.config(index))
        self.nodes.append(node)
        return node

    def certificate(self, event: Transfer, *indexes: int) -> QuorumCertificate:
        return QuorumCertificate(
            event,
            tuple(
                Vote.create(self.committee, self.members[index], event)
                for index in (indexes or (1, 2, 3))
            ),
        )

    def stop_all(self) -> None:
        for node in self.nodes:
            node.stop()


@pytest.fixture
def four(tmp_path):
    made = Committee4(tmp_path)
    yield made
    made.stop_all()


def drive(node: Node, *events: Transfer, four: Committee4) -> None:
    """Execute events on the runtime directly, as later commits do from messages."""
    for event in events:
        node._quorum.driver.handle_message(
            encode_certificate(four.certificate(event))
        )
    with node._state_lock:
        node._publish_quorum_state()


# --- With quorum=None -----------------------------------------------------


def test_default_node_has_no_runtime_and_writes_no_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    node = Node("plain", State({"alice": 10}))

    assert node._quorum is None
    assert list(tmp_path.glob("*.sqlite*")) == []
    node.stop()
    node.start()
    node.stop()


# --- Starting -------------------------------------------------------------


def test_wrong_genesis_is_refused_by_the_constructor(four):
    with pytest.raises(ValueError):
        Node("q-wrong", State({PAYER: 11}), quorum=four.config())

    assert not (four.directory / "votes-0.sqlite").exists()


def test_node_without_initial_state_is_refused(four):
    with pytest.raises(ValueError):
        Node("q-none", quorum=four.config())


def test_new_node_publishes_the_genesis(four):
    node = four.node()

    assert node.state.root() == GENESIS.root()
    assert node.events == []
    assert node.local_events == []


def test_second_node_on_the_same_file_is_refused(four):
    four.node()

    with pytest.raises(VoteStoreError):
        Node("q-other", GENESIS, quorum=four.config())


def test_stop_releases_the_file_for_a_new_node(four):
    four.node().stop()

    four.node()


def test_stop_twice_is_harmless(four):
    node = four.node()
    node.stop()
    node.stop()


def test_stopped_node_does_not_start_again(four):
    # The store is closed, and a new node is what recovers from the log.
    node = four.node()
    node.stop()

    with pytest.raises(RuntimeError):
        node.start()


def test_stop_and_start_work_on_a_running_node(four):
    node = four.node()
    node.start()
    assert node.address()[1] != 0
    node.stop()
    assert node._quorum.closed


# --- Public state ---------------------------------------------------------


def test_public_state_matches_derive_on_the_log(four):
    node = four.node()

    drive(node, A, NEXT, four=four)

    assert node.local_events == [A, NEXT]
    assert node.events == node.local_events
    assert (
        StateDeriver.apply_events(GENESIS.copy(), node.local_events).root()
        == node.state.root()
    )


def test_public_state_is_a_copy(four):
    node = four.node()
    drive(node, A, four=four)
    root = node._quorum.replica.state.root()

    node.state.balances["mallory"] = 1000
    node.local_events.clear()
    node.events.clear()

    assert node._quorum.replica.state.root() == root
    assert len(node._quorum.replica.executed) == 1


def test_restart_brings_back_state_and_log(four):
    node = four.node()
    drive(node, A, NEXT, four=four)
    root = node.state.root()
    node.stop()

    again = four.node()

    assert again.state.root() == root
    assert again.local_events == [A, NEXT]
    assert again.events == [A, NEXT]


def test_restart_does_not_bring_back_evidence(four):
    # A known limit: evidence is in memory, the votes and the log are on disk.
    node = four.node()
    node._quorum.driver.handle_message(encode_vote_request(signed(A)))
    with node._state_lock:
        node._publish_quorum_state()
    assert node.signed_events
    node.stop()

    again = four.node()

    assert again.signed_events == {}
    assert again._quorum.replica.votes() == [A]


def test_evidence_and_equivocation_are_published(four):
    node = four.node()

    for event in (A, B):
        node._quorum.driver.handle_message(encode_vote_request(signed(event)))
    with node._state_lock:
        node._publish_quorum_state()

    assert set(node.signed_events) == {A.event_id(), B.event_id()}
    assert len(node.equivocations.proofs) == 1
    assert node.equivocations.proofs[0].verify()
    # Evidence is not knowledge: nothing here counts as an event of the node.
    assert node.events == []


def test_stop_waits_for_a_message_being_handled(four):
    node = four.node()
    entered = threading.Event()
    finished = threading.Event()

    def holder():
        with node._state_lock:
            entered.set()
            finished.wait(timeout=5)

    thread = threading.Thread(target=holder, daemon=True)
    thread.start()
    assert entered.wait(timeout=5)
    stopper = threading.Thread(target=node.stop, daemon=True)
    stopper.start()
    stopper.join(timeout=0.3)
    assert stopper.is_alive()

    finished.set()
    stopper.join(timeout=5)
    thread.join(timeout=5)
    assert not stopper.is_alive()
    assert node._quorum.closed
