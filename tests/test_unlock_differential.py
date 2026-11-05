"""Differential test E: which events a closure locks, in Python and in Lean, with and without unlocking.

`QuorumUnlock.lean` proves things of `thresholdLocks`. This test checks that `EpochClosure.locks` computes the
same thing, on random reports, with reporters that repeat an event or report nothing, and with faulty
ones that report what they like. A standard committee is the same rule with a threshold of 1.

EMPIRICAL evidence of correspondence, not a refinement proof. The signatures of the reports are not read
here: `locks` does not read them, and tests/test_unlock.py covers what comes before.
"""

import os
import random
import subprocess
from pathlib import Path

import pytest

from core.attestation import Committee, EpochChange, EpochClosure, EpochReport
from core.event import Transfer
from core.signed_event import SignedTransfer
from core.state import State
from crypto.identity import Identity
from tests.test_epoch_differential import LEAN_DIR, _lake

SEEDS = (
    [20261201, 20261202, 20261203] + [20290000 + extra for extra in range(1000)]
)[: int(os.environ.get("PSYSTEM_DIFF_SEEDS", "3"))]
CASES = 200
MIN_DECISIVE = 50
SENDER = Identity.create()
KEYS = {
    count: sorted(Identity.create().public_key for _ in range(count))
    for count in (4, 6, 7, 11, 16)
}


@pytest.fixture(scope="module")
def unlock_check() -> Path:
    lake = _lake()
    if lake is None:
        pytest.skip("Lean toolchain (lake) not installed")
    build = subprocess.run(
        [lake, "build", "unlock_check"],
        cwd=LEAN_DIR,
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert build.returncode == 0, build.stdout + build.stderr
    return LEAN_DIR / ".lake" / "build" / "bin" / "unlock_check"


def number(event: Transfer) -> int:
    return int(event.event_id(), 16)


def random_case(rng: random.Random):
    unlock = rng.random() < 0.7
    f = rng.choice([1, 2, 3] if unlock else [1, 2])
    count = (5 if unlock else 3) * f + 1
    committee = Committee.create(KEYS[count], f, State({SENDER.identity_id: 10}), unlock)
    threshold = 2 * f + 1 if unlock else 1
    alternatives = [
        SignedTransfer.create(
            SENDER,
            Transfer(SENDER.identity_id, f"to-{which}", rng.randint(1, 3), nonce),
        )
        for nonce in range(rng.randint(1, 3))
        for which in range(rng.randint(1, 3))
    ]
    reporters = sorted(rng.sample(range(count), rng.randint(committee.quorum, count)))
    weights = [rng.random() for _ in alternatives]
    reports = {}

    for reporter in reporters:
        votes = [s for s, w in zip(alternatives, weights) if rng.random() < w]

        # A faulty one repeats itself. It must count once.
        if votes and rng.random() < 0.2:
            votes.append(votes[0])

        reports[reporter] = votes

    return committee, threshold, reporters, reports


def lean_lines(committee, threshold, reporters, reports) -> list[str]:
    lines = [f"N {committee.n}", f"T {threshold}"]
    lines += [f"R {reporter}" for reporter in reporters]

    for reporter, votes in reports.items():
        for signed in votes:
            event = signed.transfer
            lines.append(
                f"E {reporter} {number(event)} {event.sender} {event.receiver} {event.amount} {event.nonce}"
            )

    return lines


def python_locks(committee, reporters, reports) -> str:
    change = EpochChange("00" * 32, committee.members, committee.f)
    closure = EpochClosure(
        change,
        tuple(
            EpochReport(reporter, tuple(reports[reporter]), b"")
            for reporter in reporters
        ),
    )
    ids = sorted(number(event) for event in closure.locks(committee))
    return ",".join(map(str, ids)) if ids else "-"


@pytest.mark.parametrize("seed", SEEDS)
def test_a_closure_locks_what_the_model_says(unlock_check, tmp_path, seed):
    rng = random.Random(seed)
    cases = [random_case(rng) for _ in range(CASES)]
    path = tmp_path / "cases.txt"
    path.write_text(
        "\n---\n".join("\n".join(lean_lines(*case)) for case in cases) + "\n"
    )
    run = subprocess.run(
        [str(unlock_check), str(path)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert run.returncode == 0, run.stderr
    lean = run.stdout.splitlines()
    assert len(lean) == CASES
    unlocked_something = locked_something = 0

    for index, (case, expected) in enumerate(zip(cases, lean)):
        committee, threshold, reporters, reports = case
        found = python_locks(committee, reporters, reports)
        assert found == expected, (
            f"seed {seed} case {index}: python {found} lean {expected}\n"
            + "\n".join(lean_lines(*case))
        )
        reported = {s.transfer.canonical() for votes in reports.values() for s in votes}

        if committee.unlock and len(reported) > (0 if found == "-" else found.count(",") + 1):
            unlocked_something += 1

        if found != "-":
            locked_something += 1

    # A comparison that never reaches a rule says nothing about it.
    assert unlocked_something >= MIN_DECISIVE
    assert locked_something >= MIN_DECISIVE


def test_the_driver_counts_by_hand(unlock_check, tmp_path):
    # Fixed by hand: three reporters, threshold 2. Event 1 twice, event 2 once.
    path = tmp_path / "hand.txt"
    path.write_text(
        "N 4\nT 2\nR 0\nR 1\nR 2\n"
        "E 0 1 s r 1 0\nE 1 1 s r 1 0\nE 2 2 s q 1 0\n"
        "E 3 2 s q 1 0\n"
        "---\nN 4\nT 1\nR 0\nE 0 7 s r 1 0\n"
        "---\nN 4\nT 3\nR 0\nE 0 7 s r 1 0\n"
    )
    run = subprocess.run([str(unlock_check), str(path)], capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr
    # A member outside the reporters does not count, as member 3 here.
    assert run.stdout.splitlines() == ["1", "7", "-"]


def test_the_driver_refuses_malformed_input(unlock_check, tmp_path):
    for text in ("N x\n", "Z 1\n", "N 1\nR 5\n", "E 0 1 s\n"):
        path = tmp_path / "bad.txt"
        path.write_text(text)
        run = subprocess.run([str(unlock_check), str(path)], capture_output=True, text=True, timeout=60)
        assert run.returncode == 1, text
