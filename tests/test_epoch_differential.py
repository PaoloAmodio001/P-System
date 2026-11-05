"""Differential test D: the Python vote store across epochs vs the Lean model.

`QuorumEpochs.lean` carries `no_double_spend_across_epochs`, `closure_preserves_certified` and
`locks_carried`. This test checks, on random adversarial inputs, that one validator in Python does
what `runEpoch`, `reportOf` and `lockAllows` do: after EACH input of each epoch, the same votes, the
same closed flag, the same report. The locks of an epoch are the union of the reports of the epochs
before it, computed here and not taken from Python, which gets them from a real, verified closure.

This is EMPIRICAL evidence of correspondence for one validator, not a refinement proof. It does not
compare the verification of closures, which the model leaves to hypotheses (`ChainValid`): those
are checked in tests/test_quorum_epochs.py.

Correspondence between the two sides:

- Event ids are SHA-256 hex in Python and Nat in Lean, passed as int(hex, 16).
- Reports of other validators hold real events signed by their senders, chosen at random: any faulty
  validator could send them. An event no sender signed is refused by Python before it is a lock, and
  that lock would only block a nonce: see the limits in `QuorumEpochs.lean`.
- A restart exists only on the Python side: the store is reopened, and the model must not notice.
- A floor is applied in some epochs. Python removes the locks under it and refuses votes under it; Lean
  runs `pruneLocks` and `flooredAuth` from `QuorumSnapshot.lean`. The floors here are random, higher or
  lower than anything executed: the theorem does not need them to be true.

PSYSTEM_DIFF_SEEDS sets the number of seeds, as for the other differentials.
"""

import os
import random
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from core.attestation import (
    Committee,
    EpochChange,
    EpochClosure,
    EpochReport,
    Governance,
    Snapshot,
    Vote,
)
from core.event import Transfer
from core.signed_event import SignedTransfer
from core.state import State
from crypto.identity import Identity
from network.quorum import QuorumReplica, SqliteVoteStore

LEAN_DIR = Path(__file__).resolve().parent.parent / "formal" / "lean"
SEEDS = (
    [20261105, 20261106, 20261107] + [20280000 + extra for extra in range(1000)]
)[: int(os.environ.get("PSYSTEM_DIFF_SEEDS", "3"))]
CASES = 120
EPOCHS = 3
MIN_DECISIVE = 20

SENDERS = [Identity.create() for _ in range(2)]
GENESIS = State({sender.identity_id: 1000 for sender in SENDERS})
MEMBERS = sorted((Identity.create() for _ in range(4)), key=lambda member: member.public_key)
SIGNERS = [Identity.create() for _ in range(3)]
GOVERNANCE = Governance(tuple(sorted(signer.public_key for signer in SIGNERS)), 2)
MEMBER_KEYS = [member.public_key for member in MEMBERS]


def _lake() -> str | None:
    found = shutil.which("lake")
    if found:
        return found
    candidate = Path.home() / ".elan" / "bin" / "lake"
    return str(candidate) if candidate.exists() else None


@pytest.fixture(scope="module")
def epoch_check() -> Path:
    lake = _lake()
    if lake is None:
        pytest.skip("Lean toolchain (lake) not installed")
    build = subprocess.run(
        [lake, "build", "epoch_check"],
        cwd=LEAN_DIR,
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert build.returncode == 0, build.stdout + build.stderr
    return LEAN_DIR / ".lake" / "build" / "bin" / "epoch_check"


def lean_run(driver: Path, directory: Path, text: str) -> list[str]:
    cases = directory / "cases.txt"
    cases.write_text(text)
    run = subprocess.run([str(driver), str(cases)], capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stderr
    return run.stdout.splitlines()


def number(event: Transfer) -> int:
    return int(event.event_id(), 16)


def event_line(kind: str, event: Transfer) -> str:
    return f"{kind} {number(event)} {event.sender} {event.receiver} {event.amount} {event.nonce} -"


def ids(events) -> str:
    found = sorted({number(event) for event in events})
    return ",".join(map(str, found)) if found else "-"


class Stats:
    def __init__(self):
        self.voted = 0
        self.refused_by_lock = 0
        self.same_as_lock = 0
        self.refused_closed = 0
        self.refused_in_epoch = 0
        self.refused_by_auth = 0
        self.refused_by_floor = 0


def signed_pool(rng: random.Random) -> list[SignedTransfer]:
    pool = []
    for sender in SENDERS:
        for nonce in range(3):
            for receiver in rng.sample(["bob", "carol", "dave"], 2):
                pool.append(
                    SignedTransfer.create(
                        sender,
                        Transfer(sender.identity_id, receiver, rng.randint(1, 3), nonce),
                    )
                )
    return pool


def open_replica(path: Path, committee: Committee, refused: set, create: bool, initial: Committee):
    # The genesis committee opens the file: the chain is read back from it.
    store = SqliteVoteStore(path, initial, MEMBERS[0].public_key, create=create, governance=GOVERNANCE)
    replica = QuorumReplica(
        MEMBERS[0],
        GENESIS.copy(),
        store,
        lambda event: event.event_id() not in refused,
    )
    assert replica.committee.committee_id == committee.committee_id
    return replica, store


def closure_for(committee: Committee, replica_report, pool, rng) -> EpochClosure:
    change = EpochChange.create(committee, MEMBER_KEYS, 1, GOVERNANCE, SIGNERS[:2])
    reports = [replica_report(change.change_id)]

    # Faulty or honest, others report whatever signed events they like, each event once a nonce
    # or not: the union is what counts.
    others = rng.sample([1, 2, 3], 2)
    for validator in others:
        reports.append(
            EpochReport.create(
                committee,
                MEMBERS[validator],
                change.change_id,
                rng.sample(pool, rng.randint(0, 2)),
            )
        )

    reports.sort(key=lambda report: report.validator)
    candidate = EpochClosure(change, tuple(reports))
    event = candidate.event(GOVERNANCE, committee)
    votes = tuple(Vote.create(committee, MEMBERS[v], event) for v in range(3))
    closure = EpochClosure(change, tuple(reports), votes)
    assert closure.verify(GOVERNANCE, committee)
    return closure


def python_run(seed: int, directory: Path, stats: Stats) -> tuple[list[str], list[str]]:
    """Run every case in Python. Returns the input of the Lean driver and the lines of Python."""
    rng = random.Random(seed)
    lean_input: list[str] = []
    python: list[str] = []
    case_directory = Path(tempfile.mkdtemp(dir=directory))

    for case in range(CASES):
        path = case_directory / f"{case}.sqlite"
        pool = signed_pool(rng)
        refused = {rng.choice(pool).transfer.event_id()} if rng.random() < 0.3 else set()
        committee = Committee.create(MEMBER_KEYS, 1, GENESIS)
        initial = committee
        replica, store = open_replica(path, committee, refused, True, initial)
        locks: list[Transfer] = []
        floors: dict[str, int] = {}

        for epoch in range(EPOCHS):
            if epoch and rng.random() < 0.5:
                for sender in rng.sample(SENDERS, rng.randint(1, 2)):
                    name = sender.identity_id
                    floors[name] = max(floors.get(name, 0), rng.randint(1, 2))

                store.apply_floor(Snapshot(epoch, State({}, dict(floors)), ()))

            lines = [event_line("L", event) for event in locks]
            lines += [f"U {int(item, 16)}" for item in sorted(refused)]
            lines += [f"F {name} {nonce}" for name, nonce in sorted(floors.items())]
            closed_with: list[Transfer] | None = None

            def snapshot() -> str:
                votes = store.votes()
                report = votes if closed_with is None else closed_with
                closed = "1" if store.epoch_is_closed() else "0"
                return f"votes={ids(votes)};closed={closed};report={ids(report)}"

            python.append(snapshot())
            change = EpochChange.create(committee, MEMBER_KEYS, 1, GOVERNANCE, SIGNERS[:2])

            for _ in range(rng.randint(0, 9)):
                action = rng.random()

                if action < 0.10:
                    report = replica.report_epoch(change.change_id)
                    assert report.verify(committee, change.change_id)
                    if closed_with is None:
                        closed_with = [signed.transfer for signed in report.votes]
                    lines.append("X")
                elif action < 0.20:
                    store.close()
                    replica, store = open_replica(path, committee, refused, False, initial)
                    # A restart is no input of the model.
                    continue
                else:
                    signed = rng.choice(pool)
                    before = {e.canonical() for e in store.votes()}
                    vote = replica.handle_vote_request(signed.transfer, signed)
                    conflict_with_lock = any(
                        lock.sender == signed.transfer.sender
                        and lock.nonce == signed.transfer.nonce
                        and lock.canonical() != signed.transfer.canonical()
                        for lock in locks
                    )
                    if vote is not None:
                        stats.voted += 1
                        if signed.transfer in locks:
                            stats.same_as_lock += 1
                    elif signed.transfer.event_id() in refused:
                        stats.refused_by_auth += 1
                    elif closed_with is not None:
                        stats.refused_closed += 1
                    elif signed.transfer.nonce < floors.get(signed.transfer.sender, 0):
                        stats.refused_by_floor += 1
                    elif conflict_with_lock:
                        stats.refused_by_lock += 1
                    elif before:
                        stats.refused_in_epoch += 1
                    lines.append(event_line("V", signed.transfer))

                python.append(snapshot())

            def report_now(change_id: str) -> EpochReport:
                return replica.report_epoch(change_id)

            closure = closure_for(committee, report_now, [*pool], rng)
            lean_input.extend(lines)
            lean_input.append("---")
            python.append("---")

            for report in closure.reports:
                for signed in report.votes:
                    if signed.transfer not in locks:
                        locks.append(signed.transfer)

            following = closure.change.next_committee(committee)
            replica.install_closure(closure)
            committee = following
            assert store.committee.committee_id == committee.committee_id
            store.close()
            replica, store = open_replica(path, committee, refused, False, initial)

        store.close()

    return lean_input, python


@pytest.mark.parametrize("seed", SEEDS)
def test_one_validator_across_epochs_matches_the_model(epoch_check, tmp_path, seed):
    stats = Stats()
    directory = Path("/dev/shm") if Path("/dev/shm").is_dir() else tmp_path
    workspace = Path(tempfile.mkdtemp(dir=directory))

    try:
        lean_input, python = python_run(seed, workspace, stats)
        # Without the last separator, which would start one more, empty case.
        lean = lean_run(epoch_check, tmp_path, "\n".join(lean_input[:-1]) + "\n")
    finally:
        shutil.rmtree(workspace, ignore_errors=True)

    assert len(lean) == len(python)

    for index, (left, right) in enumerate(zip(python, lean)):
        assert left == right, f"line {index}: python {left} lean {right}"

    # A comparison that never reaches a rule says nothing about it.
    assert stats.voted >= MIN_DECISIVE
    assert stats.refused_by_lock >= MIN_DECISIVE
    assert stats.same_as_lock >= MIN_DECISIVE
    assert stats.refused_closed >= MIN_DECISIVE
    assert stats.refused_in_epoch >= MIN_DECISIVE
    assert stats.refused_by_auth >= 1
    assert stats.refused_by_floor >= MIN_DECISIVE
