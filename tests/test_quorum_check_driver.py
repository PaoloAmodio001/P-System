"""Fixed vectors for the Lean driver quorum_check, computed by hand.

The differential test trusts this driver to parse its input and to report what
runNode computes. These vectors check the driver itself: each expected line
comes from the rules of the model, not from running the driver.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

LEAN_DIR = Path(__file__).resolve().parent.parent / "formal" / "lean"
HEADER = "N 4\nQ 3\nA alice 10 0\nA bob 0 0\nA carol 0 0\n"
A = "1 alice bob 8 0 -"
B = "2 alice carol 8 0 -"


def signed(event: str) -> str:
    """An event in the form used inside a signature."""
    return event.replace(" ", "|")


def sig(validator: int, event: str, signer: int | None = None) -> str:
    made_by = validator if signer is None else signer
    return f"{validator}:{made_by}:{signed(event)}"


def sigs(event: str, *validators: int) -> str:
    return ";".join(sig(validator, event) for validator in validators)


def _lake() -> str | None:
    found = shutil.which("lake")
    if found:
        return found
    candidate = Path.home() / ".elan" / "bin" / "lake"
    return str(candidate) if candidate.exists() else None


@pytest.fixture(scope="module")
def quorum_check() -> Path:
    lake = _lake()
    if lake is None:
        pytest.skip("Lean toolchain (lake) not installed")
    build = subprocess.run(
        [lake, "build", "quorum_check"],
        cwd=LEAN_DIR,
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert build.returncode == 0, build.stdout + build.stderr
    return LEAN_DIR / ".lake" / "build" / "bin" / "quorum_check"


def _run(driver: Path, tmp_path: Path, text: str) -> subprocess.CompletedProcess:
    cases = tmp_path / "cases.txt"
    cases.write_text(text)
    return subprocess.run(
        [str(driver), str(cases)],
        capture_output=True,
        text=True,
        timeout=60,
    )


def _lines(driver: Path, tmp_path: Path, text: str) -> list[str]:
    run = _run(driver, tmp_path, text)
    assert run.returncode == 0, run.stderr
    return run.stdout.splitlines()


def _state(votes: str, executed: str, bob: int, carol: int, alice_nonce: int) -> str:
    return (
        f"votes={votes};exec={executed};"
        f"alice={10 - bob - carol}/{alice_nonce} bob={bob}/0 carol={carol}/0"
    )


def test_vote_lock_reports_each_prefix(quorum_check, tmp_path):
    text = HEADER + f"V {A}\nV {B}\nV {A}\n"
    assert _lines(quorum_check, tmp_path, text) == [
        _state("-", "-", 0, 0, 0),
        _state("1", "-", 0, 0, 0),
        _state("1", "-", 0, 0, 0),
        # Voting again for one event repeats it in the Lean list; shown once.
        _state("1", "-", 0, 0, 0),
        "---",
    ]


def test_certificate_rules(quorum_check, tmp_path):
    text = HEADER + (
        # Two signers only.
        f"C {A} {sigs(A, 0, 1)}\n"
        # A repeated signer does not count twice.
        f"C {A} {sigs(A, 0, 0, 1)}\n"
        # Signature made on another event: one bad signature invalidates it.
        f"C {A} {sigs(A, 0, 1)};{sig(2, B)};{sig(3, A)}\n"
        # Signature made by another validator.
        f"C {A} {sigs(A, 0, 1)};{sig(2, A, signer=3)}\n"
        f"C {A} {sigs(A, 0, 1, 2)}\n"
        # The conflicting event has a valid certificate, but the nonce has moved.
        f"C {B} {sigs(B, 0, 1, 2)}\n"
    )
    invalid = _state("-", "-", 0, 0, 0)
    executed = _state("-", "1", 8, 0, 1)
    assert _lines(quorum_check, tmp_path, text) == [
        invalid, invalid, invalid, invalid, invalid, executed, executed, "---",
    ]


def test_signature_binds_the_whole_event_not_only_the_id(quorum_check, tmp_path):
    # Two events with id 7. A signature on one is not valid for the other, whichever
    # field differs. This is what Python does by signing the canonical form.
    event = "7 alice bob 8 0 -"
    variants = [
        "7 alice carol 8 0 -",  # receiver
        "7 alice bob 1 0 -",  # amount
        "7 alice bob 8 1 -",  # nonce
        "7 bob bob 8 0 -",  # sender
        "7 alice bob 8 0 9",  # parents
    ]
    invalid = _state("-", "-", 0, 0, 0)
    for variant in variants:
        text = HEADER + f"C {event} {sigs(event, 0, 1)};{sig(2, variant)}\n"
        assert _lines(quorum_check, tmp_path, text) == [invalid, invalid, "---"]

    text = HEADER + f"C {event} {sigs(event, 0, 1, 2)}\n"
    assert _lines(quorum_check, tmp_path, text) == [
        invalid, _state("-", "7", 8, 0, 1), "---",
    ]


def test_same_id_with_other_content_takes_no_vote(quorum_check, tmp_path):
    other = "1 bob carol 8 0 -"
    text = HEADER + f"V {A}\nV {other}\n"
    assert _lines(quorum_check, tmp_path, text) == [
        _state("-", "-", 0, 0, 0),
        _state("1", "-", 0, 0, 0),
        _state("1", "-", 0, 0, 0),
        "---",
    ]


def test_refused_id_takes_no_vote_and_no_lock(quorum_check, tmp_path):
    text = HEADER + f"U 2\nV {B}\nV {A}\n"
    assert _lines(quorum_check, tmp_path, text) == [
        _state("-", "-", 0, 0, 0),
        _state("-", "-", 0, 0, 0),
        _state("1", "-", 0, 0, 0),
        "---",
    ]


def test_parents_and_initial_nonce(quorum_check, tmp_path):
    # alice starts at nonce 3. The first event has the right nonce and funds, but its
    # parent 9 is not executed yet.
    blocked = "5 alice bob 1 3 9"
    parent = "9 alice bob 1 3 -"
    child = "5 alice bob 1 4 9"
    text = (
        "N 4\nQ 3\nA alice 10 3\nA bob 0 0\n"
        f"C {blocked} {sigs(blocked, 0, 1, 2)}\n"
        f"C {parent} {sigs(parent, 0, 1, 2)}\n"
        f"C {child} {sigs(child, 0, 1, 2)}\n"
    )
    assert _lines(quorum_check, tmp_path, text) == [
        "votes=-;exec=-;alice=10/3 bob=0/0",
        "votes=-;exec=-;alice=10/3 bob=0/0",
        "votes=-;exec=9;alice=9/4 bob=1/0",
        "votes=-;exec=9,5;alice=8/5 bob=2/0",
        "---",
    ]


def test_several_parents_inside_a_signature(quorum_check, tmp_path):
    # Commas separate parents, semicolons separate signatures.
    first = "1 alice bob 1 0 -"
    second = "2 bob carol 1 0 -"
    child = "3 alice bob 1 1 1,2"
    text = (
        "N 4\nQ 3\nA alice 10 0\nA bob 5 0\nA carol 0 0\n"
        f"C {first} {sigs(first, 0, 1, 2)}\n"
        f"C {second} {sigs(second, 0, 1, 2)}\n"
        f"C {child} {sigs(child, 0, 1, 2)}\n"
    )
    assert _lines(quorum_check, tmp_path, text)[-2] == (
        "votes=-;exec=1,2,3;alice=8/2 bob=6/1 carol=1/0"
    )


def test_cases_are_independent(quorum_check, tmp_path):
    text = HEADER + f"V {A}\n---\n" + HEADER + f"V {B}\n"
    assert _lines(quorum_check, tmp_path, text) == [
        _state("-", "-", 0, 0, 0),
        _state("1", "-", 0, 0, 0),
        "---",
        _state("-", "-", 0, 0, 0),
        _state("2", "-", 0, 0, 0),
        "---",
    ]


@pytest.mark.parametrize(
    "bad",
    [
        "N four\n",
        "N 4\nQ 3\nV x alice bob 1 0 -\n",
        "N 4\nQ 3\nV 1 alice bob -1 0 -\n",
        "N 4\nQ 3\nV 1 alice bob 1 0\n",
        "N 4\nQ 3\nZ 1\n",
        # A signature without the signed event, or with an incomplete one.
        "N 4\nQ 3\nC 1 alice bob 1 0 - 0:0\n",
        "N 4\nQ 3\nC 1 alice bob 1 0 - 0:0:1\n",
        "N 4\nQ 3\nC 1 alice bob 1 0 - 0:0:1|alice|bob|1|0\n",
        "N 4\nQ 3\nC 1 alice bob 1 0 - 0:0:x|alice|bob|1|0|-\n",
        # A signer outside the committee cannot be represented in the model.
        "N 4\nQ 3\nC 1 alice bob 1 0 - 4:4:1|alice|bob|1|0|-\n",
    ],
)
def test_malformed_input_is_an_error(quorum_check, tmp_path, bad):
    run = _run(quorum_check, tmp_path, bad)
    assert run.returncode == 1
    assert "quorum_check:" in run.stderr
