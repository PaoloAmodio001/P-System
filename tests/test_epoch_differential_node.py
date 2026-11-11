"""Differential D through the node: a real `Node` across epochs and snapshots, with restarts, vs Lean.

Differential D (tests/test_epoch_differential.py) compares one validator's replica and store with
`runEpoch`, `reportOf` and `lockAllows`. This one sends the same kind of inputs as messages to a real
`Node`, through `_handle_peer_message`, and restarts the node, not the store:

- a vote request is `VOTE_REQUEST`, and the node votes if it answers `VOTE`;
- the end of an epoch is `EPOCH_CHANGE`, and the report is the `EPOCH_REPORT` the node answers;
- the next epoch is an `EPOCH_CLOSURE` with that report and the reports of two other members;
- a floor is a `SNAPSHOT` signed by a quorum, whose nonces are the floors, instead of `apply_floor`
  on the store. It arrives before the closure, and the node, which prunes, applies it when the
  closure installs: at the start of the next epoch, where the model has it;
- a restart stops the node and opens a new one on the same files, at any point: before a vote, while
  closed and not yet installed, right after a snapshot, right after a closure.

The oracle is the one of D: the Lean driver `epoch_check`, with the locks of an epoch computed here
from the reports of the closures, and the floors from the snapshots. After each input: the votes on
disk, whether the epoch is closed, and the report.

The timers of the rounds and the grace before a report are off: with no decision possible here (no
other member answers), a round would only move the validator out of round 0, which the model of
epochs does not have. The rounds across an epoch are in tests/test_quorum_epochs.py.

EMPIRICAL, for one node of a committee of four. PSYSTEM_DIFF_SEEDS sets the number of seeds.
"""

import hashlib
import json
import random
import shutil
import tempfile
from pathlib import Path

import pytest

from core.attestation import (
    Committee,
    EpochChange,
    EpochClosure,
    EpochReport,
    Snapshot,
    SnapshotAttestation,
)
from core.state import State
from network.message import (
    decode_epoch_report,
    encode_epoch_change,
    encode_epoch_closure,
    encode_snapshot,
    encode_vote_request,
)
from network.node import Node
from network.quorum import QuorumConfig, QuorumDriver
from network.quorum.rounds import RoundDriver
from tests.test_epoch_differential import (
    GENESIS,
    GOVERNANCE,
    MEMBER_KEYS,
    MEMBERS,
    MIN_DECISIVE,
    SEEDS,
    SENDERS,
    SIGNERS,
    epoch_check,  # noqa: F401
    event_line,
    ids,
    lean_run,
    signed_pool,
)

CASES = 60
EPOCHS = 3


@pytest.fixture(autouse=True)
def _no_timers(monkeypatch):
    monkeypatch.setattr(RoundDriver, "ROUND_FIRST_SECONDS", float("inf"))
    monkeypatch.setattr(RoundDriver, "ROUND_LONGEST_SECONDS", float("inf"))
    monkeypatch.setattr(QuorumDriver, "CLOSING_GRACE_SECONDS", 0.0)


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


class Stats:
    def __init__(self):
        self.voted = 0
        self.refused = 0
        self.closed_refusals = 0
        self.refused_by_floor = 0
        self.restart_while_closed = 0
        self.restart_after_snapshot = 0
        self.restart_after_floor = 0
        self.restart_after_closure = 0
        self.snapshots = 0


def open_node(path: Path, create: bool) -> Node:
    # The genesis committee opens the file: the chain of closures is read back from it.
    committee = Committee.create(MEMBER_KEYS, 1, GENESIS)
    return Node(
        "epoch-node",
        GENESIS.copy(),
        quorum=QuorumConfig(
            committee, MEMBERS[0], path, create=create, governance=GOVERNANCE, sync_interval=None, prune=True
        ),
    )


def send(node: Node, message: dict) -> list[dict]:
    reply = Reply()
    node._handle_peer_message(json.loads(json.dumps(message)), reply)
    return reply.sent


def snapshot_with_floors(committee: Committee, floors: dict[str, int], tag: str) -> Snapshot:
    # The ids stand for the events under the floors: one for each nonce, as a real one has.
    count = sum(floors.values())
    fake_ids = tuple(sorted(hashlib.sha256(f"{tag}-{i}".encode()).hexdigest() for i in range(count)))
    state = State(dict(GENESIS.balances), dict(floors))
    unsigned = Snapshot(committee.epoch, state, fake_ids)
    attestations = tuple(
        SnapshotAttestation.create(committee, member, unsigned.digest, ()) for member in MEMBERS[:3]
    )
    return Snapshot(committee.epoch, state, fake_ids, attestations)


def python_run(seed: int, directory: Path, stats: Stats) -> tuple[list[str], list[str]]:
    rng = random.Random(seed + 7000)
    lean_input: list[str] = []
    python: list[str] = []

    for case in range(CASES):
        path = directory / f"{case}.sqlite"
        pool = signed_pool(rng)
        committee = Committee.create(MEMBER_KEYS, 1, GENESIS)
        node = open_node(path, True)
        locks = []
        floors: dict[str, int] = {}
        floored = False

        try:
            for epoch in range(EPOCHS):
                lines = [event_line("L", event) for event in locks]
                lines += [f"F {name} {nonce}" for name, nonce in sorted(floors.items())]
                change = EpochChange.create(committee, MEMBER_KEYS, 1, GOVERNANCE, SIGNERS[:2])
                closed_with = None

                def line() -> str:
                    store = node._quorum.replica._store
                    votes = store.votes()
                    report = votes if closed_with is None else closed_with
                    closed = "1" if store.epoch_is_closed() else "0"
                    return f"votes={ids(votes)};closed={closed};report={ids(report)}"

                python.append(line())

                for _ in range(rng.randint(0, 9)):
                    action = rng.random()
                    if action < 0.12:
                        answer = send(node, encode_epoch_change(change))
                        [message] = [m for m in answer if m["type"] == "EPOCH_REPORT"]
                        _, report = decode_epoch_report(message)
                        assert report.verify(committee, change.change_id)
                        if closed_with is None:
                            closed_with = [signed.transfer for signed in report.votes]
                        lines.append("X")
                    elif action < 0.27:
                        if closed_with is not None:
                            stats.restart_while_closed += 1
                        if floored:
                            stats.restart_after_floor += 1
                        node.stop()
                        node = open_node(path, False)
                        continue
                    else:
                        signed = rng.choice(pool)
                        answer = send(node, encode_vote_request(signed))
                        voted = any(m["type"] == "VOTE" for m in answer)
                        if voted:
                            stats.voted += 1
                        elif closed_with is not None:
                            stats.closed_refusals += 1
                        elif signed.transfer.nonce < floors.get(signed.transfer.sender, 0):
                            stats.refused_by_floor += 1
                        else:
                            stats.refused += 1
                        lines.append(event_line("V", signed.transfer))
                    python.append(line())

                # The report of this node, asked for again if it has not reported: the same order.
                answer = send(node, encode_epoch_change(change))
                [message] = [m for m in answer if m["type"] == "EPOCH_REPORT"]
                _, own = decode_epoch_report(message)
                reports = [own]
                for validator in rng.sample([1, 2, 3], 2):
                    reports.append(
                        EpochReport.create(
                            committee, MEMBERS[validator], change.change_id, rng.sample(pool, rng.randint(0, 2))
                        )
                    )
                reports.sort(key=lambda report: report.validator)
                closure = EpochClosure(change, tuple(reports))
                assert closure.verify(GOVERNANCE, committee)

                lean_input.extend(lines)
                lean_input.append("---")
                python.append("---")

                for report in closure.reports:
                    for signed in report.votes:
                        if signed.transfer not in locks:
                            locks.append(signed.transfer)

                floored = False
                if epoch + 1 < EPOCHS and rng.random() < 0.5:
                    for sender in rng.sample(SENDERS, rng.randint(1, 2)):
                        name = sender.identity_id
                        floors[name] = max(floors.get(name, 0), rng.randint(1, 2))
                    snapshot = snapshot_with_floors(committee, floors, f"{seed}-{case}-{epoch}")
                    send(node, encode_snapshot(snapshot))
                    assert node._quorum.replica.base is not None
                    assert node._quorum.replica.base.digest == snapshot.digest
                    stats.snapshots += 1
                    floored = True
                    if rng.random() < 0.5:
                        # A restart between the snapshot and the closure that applies its floor.
                        stats.restart_after_snapshot += 1
                        node.stop()
                        node = open_node(path, False)

                send(node, encode_epoch_closure(closure))
                committee = closure.change.next_committee(committee)
                assert node._quorum.replica.committee.committee_id == committee.committee_id

                if rng.random() < 0.5:
                    stats.restart_after_closure += 1
                    node.stop()
                    node = open_node(path, False)
        finally:
            node.stop()

    return lean_input, python


@pytest.mark.parametrize("seed", SEEDS)
def test_a_node_across_epochs_and_snapshots_matches_the_model(epoch_check, tmp_path, seed):  # noqa: F811
    stats = Stats()
    directory = Path("/dev/shm") if Path("/dev/shm").is_dir() else tmp_path
    workspace = Path(tempfile.mkdtemp(dir=directory))

    try:
        lean_input, python = python_run(seed, workspace, stats)
        lean = lean_run(epoch_check, tmp_path, "\n".join(lean_input[:-1]) + "\n")
    finally:
        shutil.rmtree(workspace, ignore_errors=True)

    assert len(lean) == len(python)
    for index, (left, right) in enumerate(zip(python, lean)):
        assert left == right, f"line {index}: python {left} lean {right}"

    print(f"\nseed {seed}: {vars(stats)}")
    for name, value in vars(stats).items():
        assert value >= MIN_DECISIVE, f"{name} exercised {value} times"
