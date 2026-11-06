"""A test must leave no node alive, whatever way it ends.

Three processes of a node were once found alive six hours after a run. The ways out, each tried here on
a real deployment in a real pytest: a test that fails, a fixture that fails while starting, a pytest told
to stop, and a mutation that hangs, whose pytest gets killed. A SIGKILL of pytest itself, from outside,
cannot be handled from inside it: `run_tests_on` kills the whole group for that reason.
"""

import os
import signal
import subprocess
import sys
import textwrap
import time

import pytest

from tests import mutation_support
from tests.deployment_helpers import ROOT, wait_until

# Four real nodes for each of five tests: half a minute.
pytestmark = pytest.mark.slow


def alive_under(directory) -> list[str]:
    """The processes whose command line names `directory`, not counting this search."""
    result = subprocess.run(["pgrep", "-af", f"network.cli node .*{directory}"], capture_output=True, text=True)
    return [line for line in result.stdout.splitlines() if "pgrep" not in line]


def gone(directory, seconds: float = 15.0) -> bool:
    return wait_until(lambda: not alive_under(directory), seconds)


HEADER = """
import time
from pathlib import Path
import pytest
from tests.deployment_helpers import Deployment
BASE = Path({base!r})
"""


def write_test(tmp_path, body: str):
    base = tmp_path / "deployment"
    base.mkdir()
    test = tmp_path / "test_child.py"
    test.write_text(HEADER.format(base=str(base)) + textwrap.dedent(body))
    return test, base


def run_pytest(test) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "tests.conftest", "-p", "no:cacheprovider", "--rootdir", str(test.parent), str(test)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_a_test_that_fails_leaves_no_node(tmp_path):
    test, base = write_test(tmp_path, """
        def test_it():
            made = Deployment(BASE)
            made.start_all()
            assert False
    """)
    result = run_pytest(test)
    assert result.returncode == 1, result.stdout + result.stderr
    assert gone(base), alive_under(base)


def test_a_fixture_that_fails_after_starting_leaves_no_node(tmp_path):
    test, base = write_test(tmp_path, """
        @pytest.fixture
        def running():
            made = Deployment(BASE)
            made.start_all()
            assert False
            yield made
            made.stop_all()

        def test_it(running):
            pass
    """)
    result = run_pytest(test)
    assert result.returncode == 1, result.stdout + result.stderr
    assert gone(base), alive_under(base)


def test_a_start_that_fails_half_way_leaves_no_node(tmp_path):
    test, base = write_test(tmp_path, """
        def test_it():
            made = Deployment(BASE)
            (made.directory(2) / "node.toml").write_text("not a configuration")
            made.start_all()
    """)
    result = run_pytest(test)
    assert result.returncode == 1, result.stdout + result.stderr
    assert gone(base), alive_under(base)


def test_a_pytest_told_to_stop_leaves_no_node(tmp_path):
    test, base = write_test(tmp_path, """
        def test_it():
            made = Deployment(BASE)
            made.start_all()
            print("UP", flush=True)
            time.sleep(300)
    """)
    process = subprocess.Popen(
        [sys.executable, "-m", "pytest", "-q", "-s", "-p", "tests.conftest", "-p", "no:cacheprovider", "--rootdir", str(test.parent), str(test)],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        assert wait_until(lambda: len(alive_under(base)) == 4, 60)
        process.send_signal(signal.SIGTERM)
        process.wait(timeout=60)
        assert gone(base), alive_under(base)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()

        for line in alive_under(base):
            os.kill(int(line.split()[0]), signal.SIGKILL)

        process.stdout.close()


def test_a_mutation_that_hangs_leaves_no_node(tmp_path, monkeypatch):
    test, base = write_test(tmp_path, """
        def test_it():
            made = Deployment(BASE)
            made.start_all()
            time.sleep(300)
    """)
    monkeypatch.setattr(mutation_support, "HANG_SECONDS", 25)
    source = (ROOT / "core" / "state.py").read_text()

    try:
        result = mutation_support.run_tests_on("core.state", source, [str(test), "--rootdir", str(test.parent), "-p", "tests.conftest"])
        assert result.stdout == "HUNG" and result.returncode == 1
        assert gone(base), alive_under(base)
    finally:
        for line in alive_under(base):
            os.kill(int(line.split()[0]), signal.SIGKILL)
