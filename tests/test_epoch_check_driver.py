"""Fixed vectors for the Lean driver epoch_check, computed by hand from the rules of the model."""

import subprocess

import pytest

from tests.test_epoch_differential import epoch_check, lean_run  # noqa: F401

A = "1 alice bob 8 0 -"
B = "2 alice carol 8 0 -"
C = "3 alice bob 1 1 -"


def state(votes: str, closed: int, report: str) -> str:
    return f"votes={votes};closed={closed};report={report}"


def run(driver, tmp_path, *lines):
    return lean_run(driver, tmp_path, "\n".join(lines) + "\n")


def test_no_inputs(epoch_check, tmp_path):  # noqa: F811
    assert run(epoch_check, tmp_path, "U 9") == [state("-", 0, "-"), "---"]


def test_first_vote_holds_the_nonce(epoch_check, tmp_path):  # noqa: F811
    assert run(epoch_check, tmp_path, f"V {A}", f"V {B}", f"V {A}", f"V {C}") == [
        state("-", 0, "-"),
        state("1", 0, "1"),
        state("1", 0, "1"),
        state("1", 0, "1"),
        state("1,3", 0, "1,3"),
        "---",
    ]


def test_nothing_after_close_and_the_report_is_of_the_first_close(epoch_check, tmp_path):  # noqa: F811
    assert run(epoch_check, tmp_path, f"V {A}", "X", f"V {C}", "X") == [
        state("-", 0, "-"),
        state("1", 0, "1"),
        state("1", 1, "1"),
        state("1", 1, "1"),
        state("1", 1, "1"),
        "---",
    ]


def test_a_lock_allows_only_its_event(epoch_check, tmp_path):  # noqa: F811
    assert run(epoch_check, tmp_path, f"L {A}", f"V {B}", f"V {A}") == [
        state("-", 0, "-"),
        state("-", 0, "-"),
        state("1", 0, "1"),
        "---",
    ]


def test_two_locks_block_the_nonce(epoch_check, tmp_path):  # noqa: F811
    assert run(epoch_check, tmp_path, f"L {A}", f"L {B}", f"V {A}", f"V {B}", f"V {C}") == [
        state("-", 0, "-"),
        state("-", 0, "-"),
        state("-", 0, "-"),
        state("3", 0, "3"),
        "---",
    ]


def test_a_refused_id_gets_no_vote(epoch_check, tmp_path):  # noqa: F811
    assert run(epoch_check, tmp_path, "U 1", f"V {A}", f"V {B}") == [
        state("-", 0, "-"),
        state("-", 0, "-"),
        state("2", 0, "2"),
        "---",
    ]


def test_cases_are_separate(epoch_check, tmp_path):  # noqa: F811
    assert run(epoch_check, tmp_path, f"L {A}", "---", f"V {B}") == [
        state("-", 0, "-"),
        "---",
        state("-", 0, "-"),
        state("2", 0, "2"),
        "---",
    ]


@pytest.mark.parametrize(
    "text",
    [
        "Z\n",
        "V 1 alice bob 8 0\n",
        "V x alice bob 8 0 -\n",
        "V 1 alice bob -8 0 -\n",
        "L 1 alice bob 8 zero -\n",
        "U one\n",
        "X now\n",
        "X\nL 1 alice bob 8 0 -\n",
        "X\nU 1\n",
    ],
)
def test_malformed_input_is_an_error(epoch_check, tmp_path, text):  # noqa: F811
    cases = tmp_path / "cases.txt"
    cases.write_text(text)
    run_result = subprocess.run([str(epoch_check), str(cases)], capture_output=True, text=True)
    assert run_result.returncode == 1
