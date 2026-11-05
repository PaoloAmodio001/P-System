"""The fast suite must leave out what it claims to leave out, and nothing else."""

import re
import subprocess
import sys
from pathlib import Path

CONFTEST = Path(__file__).with_name("conftest.py")
# What a file of mutations or a differential does, whatever it is called.
SLOW_WORK = re.compile(r"quorum_check|PSYSTEM_DIFF_SEEDS|\.replace\(old, new\)")
RULE = '    return name.endswith("_mutations.py") or "differential" in name\n'
# Runs the Lean driver on vectors written by hand, in a moment: not a differential.
FAST_ON_PURPOSE = {"test_quorum_check_driver.py"}


def slow_work_outside_the_rule(directory: Path, is_slow) -> list[str]:
    return sorted(
        path.name
        for path in directory.glob("test_*.py")
        if path.name != Path(__file__).name
        and path.name not in FAST_ON_PURPOSE
        and not is_slow(path.name)
        and SLOW_WORK.search(path.read_text())
    )


def fast_selection(directory: Path, conftest: str) -> set[str]:
    """The files that `-m "not slow"` runs, given this conftest."""
    (directory / "conftest.py").write_text(conftest)
    for name in (
        "test_x_mutations.py",
        "test_quorum_differential_x.py",
        "test_plain.py",
    ):
        (directory / name).write_text("def test_it():\n    pass\n")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--collect-only",
            "-m",
            "not slow",
            "-p",
            "no:cacheprovider",
        ],
        cwd=directory,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return {
        line.split("::")[0]
        for line in result.stdout.splitlines()
        if "::" in line
    }


def test_the_fast_suite_leaves_out_mutations_and_differentials(tmp_path):
    assert fast_selection(tmp_path, CONFTEST.read_text()) == {"test_plain.py"}


def test_this_check_fails_if_the_rule_marks_nothing(tmp_path):
    source = CONFTEST.read_text()
    assert source.count(RULE) == 1

    selected = fast_selection(tmp_path, source.replace(RULE, "    return False\n"))

    assert selected == {
        "test_plain.py",
        "test_x_mutations.py",
        "test_quorum_differential_x.py",
    }


def test_no_slow_work_escapes_under_another_name():
    from tests.conftest import is_slow_file

    assert slow_work_outside_the_rule(CONFTEST.parent, is_slow_file) == []


def test_that_check_sees_a_file_under_another_name(tmp_path):
    from tests.conftest import is_slow_file

    (tmp_path / "test_innocent.py").write_text("source.replace(old, new)\n")
    (tmp_path / "test_x_mutations.py").write_text("source.replace(old, new)\n")

    assert slow_work_outside_the_rule(tmp_path, is_slow_file) == ["test_innocent.py"]
