"""Quorum mode against a sender that lies and a member of the committee that lies.

The historical mode without a committee forked under this dissemination, and it has been removed.
Here the same dissemination gives none, for every way it can go: all the ways the honest
nodes can vote, all that the faulty member can sign, all that can reach each node. The
hypothesis is tested too: with more than f faulty members the fork comes back.

All of this is EMPIRICAL, for n = 4 and f = 1, through real Nodes. The theorem on the model
is no_double_spend, in formal/lean/PSystem/QuorumSafety.lean.
"""

import itertools
import json
import random
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

from core.attestation import Committee, QuorumCertificate, Vote
from core.event import Transfer
from core.signed_event import SignedTransfer
from core.state import State
from crypto.identity import Identity
from network.message import (
    decode_vote,
    encode_certificate,
    encode_vote_request,
)
from network.node import Node
from network.peer import Peer
from network.quorum import QuorumConfig
from tests import quorum_store_worker as worker
from tests.die_with_parent import command
from tests.test_quorum_driver import GENESIS as DRIVER_GENESIS
from tests.test_quorum_driver import _spends

SENDER = Identity.create()
PAYER = SENDER.identity_id
GENESIS = State({PAYER: 10})
A = Transfer(PAYER, "bob", 8, 0)
B = Transfer(PAYER, "carol", 8, 0)
MEMBERS = sorted(
    (Identity.create() for _ in range(4)),
    key=lambda identity: identity.public_key,
)
COMMITTEE = Committee.create([m.public_key for m in MEMBERS], 1, GENESIS)
# Written here, not read from the committee: this is what the test claims.
QUORUM_OF_FOUR = 3


def request(event: Transfer, identity: Identity = SENDER) -> dict:
    return json.loads(
        json.dumps(encode_vote_request(SignedTransfer.create(identity, event)))
    )


class Reply:
    def __init__(self):
        self.sent = []

    def send(self, message):
        self.sent.append(json.loads(json.dumps(message)))

    def enqueue(self, message):

        self.send(message)

        return 0


    def charge(self, tokens):

        pass


def open_node(path: Path, index: int, committee=COMMITTEE, genesis=GENESIS, create=True):
    return Node(
        f"byz-{index}",
        genesis,
        quorum=QuorumConfig(committee, MEMBERS[index], path, create=create),
    )


def ask_for_vote(node: Node, event: Transfer) -> Vote | None:
    reply = Reply()
    node._handle_peer_message(request(event), reply)
    return decode_vote(reply.sent[0])[1] if reply.sent else None


def deliver(node: Node, certificate: QuorumCertificate) -> None:
    node._handle_peer_message(json.loads(json.dumps(encode_certificate(certificate))))


def executed(node: Node) -> list[Transfer]:
    return list(node.local_events)


# What the faulty member signs, with its real key.
FAULTY_SIGNS = {
    "both": (A, B),
    "only a": (A,),
    "only b": (B,),
    "nothing": (),
}
# What reaches a node of what the attacker could put together.
DELIVERIES = {
    "a then b": "ab",
    "b then a": "ba",
    "only a": "a",
    "only b": "b",
    "none": "",
}


@pytest.mark.parametrize("faulty", FAULTY_SIGNS)
def test_no_fork_for_any_vote_any_signature_and_any_delivery(tmp_path, faulty):
    """
    Members 0, 1 and 2 are honest and 3 is faulty. The sender signs two versions, and each
    honest node gets one of them first. The attacker then asks each node for the other
    one too, signs what it wants with the key of member 3, and hands out all it has.
    """
    runs = 0
    outcomes = set()

    for first_seen in itertools.product("ab", repeat=3):
        directory = tmp_path / "".join(first_seen)
        directory.mkdir()
        events = {"a": A, "b": B}
        votes = {"a": [], "b": []}

        # What each honest node signs. One store per node, once.
        for index, name in enumerate(first_seen):
            node = open_node(directory / f"{index}.sqlite", index)
            vote = ask_for_vote(node, events[name])
            assert vote is not None
            votes[name].append(vote)

            # The other version gets no signature from an honest node.
            other = "b" if name == "a" else "a"
            assert ask_for_vote(node, events[other]) is None
            node.stop()

        for event in FAULTY_SIGNS[faulty]:
            name = "a" if event == A else "b"
            votes[name].append(Vote.create(COMMITTEE, MEMBERS[3], event))

        certificates = {
            name: QuorumCertificate(events[name], tuple(votes[name])) for name in "ab"
        }
        # A certificate of votes of round 0 decides with all four of them; with three it only
        # prepares, and nothing runs on it alone (formal/lean/PSystem/QuorumRounds.lean).
        prepared = {name for name in "ab" if len(votes[name]) >= QUORUM_OF_FOUR}
        assert len(prepared) <= 1, "two quorums: the counting itself would be wrong"
        valid = {name for name in "ab" if len(votes[name]) >= COMMITTEE.n}

        for pattern in itertools.product(DELIVERIES.values(), repeat=3):
            runs += 1
            nodes = [
                open_node(directory / f"{index}.sqlite", index, create=False)
                for index in range(3)
            ]
            try:
                for node, delivery in zip(nodes, pattern):
                    for name in delivery:
                        deliver(node, certificates[name])

                results = [tuple(executed(node)) for node in nodes]

                for node, delivery, result in zip(nodes, pattern, results):
                    received_valid = valid & set(delivery)
                    expected = (
                        (events[next(iter(received_valid))],) if received_valid else ()
                    )
                    assert result == expected, (first_seen, faulty, pattern)
                    # One certificate is not valid, so nothing here is a conflict.
                    assert not node.conflicted

                # The fork: two honest nodes, two alternatives.
                assert len({r for r in results if r}) <= 1
                outcomes.add(tuple(sorted(valid)))
            finally:
                for node in nodes:
                    node.stop()
            _undo_executions(directory)

    assert runs == 8 * 125
    # The cases were not all the same one. A decision needs the three honest votes on one side
    # (3-0 or 0-3) and the faulty member signing that side too.
    expected_outcomes = {
        "both": {("a",), ("b",), ()},
        "only a": {("a",), ()},
        "only b": {("b",), ()},
        "nothing": {()},
    }[faulty]
    assert outcomes == expected_outcomes


def _undo_executions(directory: Path) -> None:
    # The votes stay, and only what the deliveries of this run added goes away, so that
    # the next pattern starts from what the voting left.
    for path in directory.glob("*.sqlite"):
        connection = sqlite3.connect(path)
        connection.execute("DELETE FROM certificates")
        connection.execute("DELETE FROM decided")
        connection.execute("DELETE FROM halt")
        connection.commit()
        connection.close()


def test_forged_signatures_of_honest_members_make_no_quorum(tmp_path):
    # The faulty member signs for real, and has to invent the other three: a decision of round 0
    # takes all four. Honest member 0 voted a, and the attacker wants b.
    node = open_node(tmp_path / "0.sqlite", 0)
    assert ask_for_vote(node, A) is not None
    real = Vote.create(COMMITTEE, MEMBERS[3], B)
    honest_on_other_event = [Vote.create(COMMITTEE, MEMBERS[i], A) for i in (0, 1, 2)]
    reused = [
        Vote(vote.validator, vote.signature) for vote in honest_on_other_event
    ]
    invented = [Vote(0, bytes((5,)) * 64), Vote(1, bytes(64)), Vote(2, bytes((7,)) * 64)]

    for votes in (reused, invented, [real, real, real]):
        deliver(node, QuorumCertificate(B, (real, *votes)))

    assert executed(node) == []
    assert not node.conflicted
    node.stop()


def test_a_node_that_voted_the_other_version_follows_a_commit(tmp_path):
    # After a split, the rounds can decide the version a node did not vote for in round 0: its vote
    # of round 0 must not stop it from executing the decision (`decisions_agree`).
    from core.attestation import PRECOMMIT

    node = open_node(tmp_path / "0.sqlite", 0)
    assert ask_for_vote(node, B) is not None
    precommits = tuple(Vote.create_phase(COMMITTEE, MEMBERS[i], A, PRECOMMIT, 1) for i in (1, 2, 3))
    deliver(node, QuorumCertificate(A, precommits, phase=PRECOMMIT, round=1))

    assert executed(node) == [A]
    assert not node.conflicted
    node.stop()


def test_votes_split_with_a_faulty_member_silent_give_no_certificate(tmp_path):
    # Two votes for one and one for the other, and the fourth is silent: nothing passes,
    # and the sender is stuck. No node chose, and liveness is not claimed.
    nodes = [open_node(tmp_path / f"{i}.sqlite", i) for i in range(3)]
    votes_a = [ask_for_vote(nodes[0], A), ask_for_vote(nodes[1], A)]
    votes_b = [ask_for_vote(nodes[2], B)]

    for node in nodes:
        deliver(node, QuorumCertificate(A, tuple(votes_a)))
        deliver(node, QuorumCertificate(B, tuple(votes_b)))

    for node in nodes:
        assert executed(node) == []
        assert node.state.root() == GENESIS.root()
        node.stop()


def _two_faulty_members_certify_both(tmp_path):
    """More faulty members than f = 1: members 2 and 3 sign both versions."""
    first = open_node(tmp_path / "0.sqlite", 0)
    second = open_node(tmp_path / "1.sqlite", 1)
    faulty = [MEMBERS[2], MEMBERS[3]]
    prepare_a = QuorumCertificate(
        A,
        (ask_for_vote(first, A), *(Vote.create(COMMITTEE, m, A) for m in faulty)),
    )
    prepare_b = QuorumCertificate(
        B,
        (ask_for_vote(second, B), *(Vote.create(COMMITTEE, m, B) for m in faulty)),
    )
    # Each honest node precommits on the prepare certificate it sees, as it should; with the two
    # faulty precommits that is a commit certificate for each version.
    certificates = []
    for node, prepare in ((first, prepare_a), (second, prepare_b)):
        deliver(node, prepare)
        own = node._quorum.replica.sign_phase(prepare.event, "precommit", 0)
        precommits = (own, *(Vote.create_phase(COMMITTEE, m, prepare.event, "precommit", 0) for m in faulty))
        certificates.append(
            QuorumCertificate(prepare.event, tuple(sorted(precommits, key=lambda v: v.validator)), 0, "precommit", 0)
        )
    return first, second, *certificates


def test_beyond_f_faulty_members_the_fork_comes_back(tmp_path):
    # The hypothesis of the theorem matters: this is what it excludes. Without this test,
    # the one above could pass for reasons that have nothing to do with the quorum.
    first, second, certificate_a, certificate_b = _two_faulty_members_certify_both(tmp_path)

    deliver(first, certificate_a)
    deliver(second, certificate_b)

    assert executed(first) == [A]
    assert executed(second) == [B]
    assert first.state.balance("bob") == 8
    assert second.state.balance("carol") == 8
    first.stop()
    second.stop()


def test_beyond_f_a_node_that_sees_both_halts_and_chooses_nothing(tmp_path):
    first, second, certificate_a, certificate_b = _two_faulty_members_certify_both(tmp_path)

    deliver(first, certificate_a)
    root = first.state.root()
    deliver(first, certificate_b)

    assert first.conflicted
    assert executed(first) == [A]
    assert first.state.root() == root
    first.stop()
    second.stop()


# --- The order of arrival, on a Node --------------------------------------


@pytest.mark.parametrize("seed", range(6))
def test_permutations_of_the_same_certificates_give_the_same_node(tmp_path, seed):
    rng = random.Random(seed)
    committee = Committee.create([m.public_key for m in MEMBERS], 1, DRIVER_GENESIS)
    events = _spends(rng)
    certificates = [
        QuorumCertificate(
            event,
            tuple(Vote.create(committee, MEMBERS[i], event) for i in (0, 1, 2, 3)),
        )
        for event in events
    ]
    results = set()

    for attempt in range(6):
        order = list(certificates)
        rng.shuffle(order)
        node = open_node(
            tmp_path / f"{attempt}.sqlite", 0, committee, DRIVER_GENESIS
        )
        for certificate in order:
            deliver(node, certificate)
        results.add(
            (node.state.root(), frozenset(e.canonical() for e in node.local_events))
        )
        assert not node.conflicted
        node.stop()

    assert len(results) == 1


def test_a_decision_waiting_at_a_restart_survives_it(tmp_path):
    path = tmp_path / "votes.sqlite"
    node = open_node(path, 0)
    child = Transfer(PAYER, "bob", 1, 1, (A.event_id(),))

    def certificate(event):
        return QuorumCertificate(
            event,
            tuple(Vote.create(COMMITTEE, MEMBERS[i], event) for i in (0, 1, 2, 3)),
        )

    deliver(node, certificate(child))
    assert executed(node) == []
    node.stop()

    # The decision of the child is on disk (schema 8): the parent alone brings it back.
    node = open_node(path, 0, create=False)
    deliver(node, certificate(A))
    assert executed(node) == [A, child]
    node.stop()


# --- Death of the process -------------------------------------------------


def _spawn_worker(mode: str, path: Path) -> tuple[subprocess.Popen, list[str]]:
    process = subprocess.Popen(
        command(worker.__file__, mode, str(path)),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    line = process.stdout.readline().split()
    assert line, process.stderr.read()
    return process, line


def _worker_node(path: Path) -> Node:
    return Node(
        "after-kill",
        State(worker.HALT_GENESIS),
        quorum=QuorumConfig(worker.HALT_COMMITTEE, worker.HALT_IDENTITIES[0], path),
    )


def _kill(process: subprocess.Popen) -> None:
    process.send_signal(signal.SIGKILL)
    process.wait(timeout=10)


def test_halt_survives_the_death_of_the_process(tmp_path):
    path = tmp_path / "votes.sqlite"
    process, line = _spawn_worker("hold-node-halted", path)
    assert line == ["HALTED", "CONFLICTED"]
    _kill(process)

    node = _worker_node(path)

    assert node.conflicted
    assert not node.submit(
        SignedTransfer.create(worker.VOTE_SENDER, worker.VOTED_EVENT)
    )
    node.stop()


def test_vote_survives_the_death_of_the_process(tmp_path):
    path = tmp_path / "votes.sqlite"
    process, line = _spawn_worker("hold-node-voted", path)
    assert line[0] == "VOTED"
    _kill(process)

    node = _worker_node(path)

    def answer(event):
        reply = Reply()
        node._handle_peer_message(
            request(event, worker.VOTE_SENDER),
            reply,
        )
        return reply.sent

    # The alternative gets nothing, and the same event the same signature as before.
    assert answer(worker.ALTERNATIVE_EVENT) == []
    assert answer(worker.VOTED_EVENT)[0]["signature"] == line[1]
    node.stop()


# --- Real TLS -------------------------------------------------------------


def _wait_until(condition, seconds: float = 15.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return condition()


@pytest.fixture
def tls_nodes(tmp_path):
    tag = tmp_path.name[-12:].replace("_", "-")
    nodes = [
        Node(
            f"tls-{tag}-{index}",
            GENESIS,
            quorum=QuorumConfig(
                COMMITTEE,
                MEMBERS[index],
                tmp_path / f"{index}.sqlite",
                create=True,
            ),
        )
        for index in range(4)
    ]
    for node in nodes:
        node.start()

    for low, high in itertools.combinations(nodes, 2):
        host, port = high.address()
        assert low.connect_peer(Peer(node_id=high.node_id, host=host, port=port))

    assert _wait_until(
        lambda: all(len(node.peer_connections) == 3 for node in nodes)
    )
    yield nodes
    for node in nodes:
        node.stop()


@pytest.mark.filterwarnings("error::pytest.PytestUnhandledThreadExceptionWarning")
def test_event_runs_on_four_nodes_over_real_tls(tls_nodes):
    assert tls_nodes[0].submit(SignedTransfer.create(SENDER, A))

    # The node publishes its events and then its state: wait for both.
    assert _wait_until(
        lambda: all(n.local_events == [A] and n.state.balance("bob") == 8 for n in tls_nodes)
    )


@pytest.mark.filterwarnings("error::pytest.PytestUnhandledThreadExceptionWarning")
def test_node_that_voted_the_alternative_follows_over_real_tls(tls_nodes):
    # Asked by a peer, on a real connection, as a faulty sender would.
    voted_b = tls_nodes[3]
    tls_nodes[1].peer_connections[voted_b.node_id].send(
        encode_vote_request(SignedTransfer.create(SENDER, B))
    )
    assert _wait_until(lambda: voted_b._quorum.replica.votes() == [B])

    assert tls_nodes[0].submit(SignedTransfer.create(SENDER, A))

    assert _wait_until(lambda: all(n.local_events == [A] for n in tls_nodes))
    assert voted_b._quorum.replica.votes() == [B]
    assert voted_b.state.balance("carol") == 0
    for node in tls_nodes:
        assert not node.conflicted
