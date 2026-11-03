"""Differential test: Python StateDeriver vs the Lean model `derive`.

The Lean model (formal/lean/PSystem/Derive.lean) carries the convergence
theorems (Convergence, Soundness, Completeness, Agreement). This test checks,
on random histories, that the Python implementation computes the same result
as that model: the same balances and nonces, or a rejection in both.

This is EMPIRICAL evidence of correspondence, not a refinement proof.

Event ids: Python uses SHA-256 hex strings, Lean uses Nat. Ids are passed as
int(hex, 16); for fixed-length hex strings this preserves the order used by
the deterministic choice.
"""

import random
import shutil
import subprocess
from pathlib import Path

import pytest

from core.derive import StateDeriver
from core.event import Transfer
from core.state import State

LEAN_DIR = Path(__file__).resolve().parent.parent / "formal" / "lean"
ACCOUNTS = ["alice", "bob", "carol", "dave"]
CASES = 3000
SEED = 20261103


def _lake() -> str | None:
    found = shutil.which("lake")
    if found:
        return found
    candidate = Path.home() / ".elan" / "bin" / "lake"
    return str(candidate) if candidate.exists() else None


@pytest.fixture(scope="module")
def derive_check() -> Path:
    lake = _lake()
    if lake is None:
        pytest.skip("Lean toolchain (lake) not installed")
    build = subprocess.run(
        [lake, "build", "derive_check"],
        cwd=LEAN_DIR,
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert build.returncode == 0, build.stdout + build.stderr
    return LEAN_DIR / ".lake" / "build" / "bin" / "derive_check"


def _random_case(rng: random.Random):
    balances = {name: rng.randint(0, 10) for name in ACCOUNTS}
    events: list[Transfer] = []
    sent = {name: 0 for name in ACCOUNTS}

    for _ in range(rng.randint(0, 7)):
        sender = rng.choice(ACCOUNTS)
        receiver = rng.choice(ACCOUNTS)
        if receiver == sender and rng.random() < 0.9:
            receiver = rng.choice([a for a in ACCOUNTS if a != sender])

        parents: tuple[str, ...] = ()
        if events and rng.random() < 0.4:
            chosen = rng.sample(events, k=min(len(events), rng.randint(1, 2)))
            parents = tuple(parent.event_id() for parent in chosen)
        if rng.random() < 0.03:
            parents += ("%064x" % rng.getrandbits(256),)

        # Mostly the next nonce of the sender, sometimes a wrong one.
        nonce = sent[sender] if rng.random() < 0.85 else rng.randint(0, 3)
        sent[sender] += 1

        events.append(
            Transfer(
                sender=sender,
                receiver=receiver,
                amount=rng.choice([0, 1, 1, 2, 2, 3, 4]),
                nonce=nonce,
                parents=parents,
            )
        )

    if events and rng.random() < 0.05:
        events.append(rng.choice(events))
    rng.shuffle(events)
    return balances, events


def _python_result(balances, events) -> str:
    initial = State(balances=dict(balances), nonces={})
    try:
        final = StateDeriver.apply_events(initial, events)
    except ValueError:
        return "REJECT"
    return "OK " + " ".join(
        f"{name}={final.balance(name)}/{final.nonce(name)}" for name in ACCOUNTS
    )


def _lean_case(balances, events) -> str:
    lines = [f"A {name} {balances[name]}" for name in ACCOUNTS]
    for event in events:
        parents = ",".join(str(int(p, 16)) for p in event.parents) or "-"
        lines.append(
            f"E {int(event.event_id(), 16)} {event.sender} {event.receiver} "
            f"{event.amount} {event.nonce} {parents}"
        )
    return "\n".join(lines)


def test_python_matches_lean_model(derive_check, tmp_path):
    rng = random.Random(SEED)
    cases = [_random_case(rng) for _ in range(CASES)]

    cases_file = tmp_path / "cases.txt"
    cases_file.write_text("\n---\n".join(_lean_case(*case) for case in cases) + "\n")

    run = subprocess.run(
        [str(derive_check), str(cases_file)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert run.returncode == 0, run.stderr
    lean_results = run.stdout.splitlines()
    assert len(lean_results) == CASES

    python_results = [_python_result(*case) for case in cases]

    mismatches = [
        (index, cases[index], python_results[index], lean_results[index])
        for index in range(CASES)
        if python_results[index] != lean_results[index]
    ]
    assert not mismatches, "first mismatches:\n" + "\n".join(
        f"case {i}: python={p!r} lean={l!r}\n  {c!r}" for i, c, p, l in mismatches[:3]
    )

    # The comparison must exercise both outcomes, not only rejections.
    accepted = sum(result.startswith("OK") for result in python_results)
    nontrivial = sum(
        result.startswith("OK") and len(case[1]) >= 3
        for case, result in zip(cases, python_results)
    )
    assert accepted >= CASES // 5
    assert CASES // 5 <= CASES - accepted
    assert nontrivial >= 100
