"""A test must leave no node alive, whatever way it ends.

Three processes of a node were once found alive six hours after a run. The ways out, each tried here on
a real deployment in a real pytest: a test that fails, a fixture that fails while starting, a pytest told
to stop, a pytest killed half way, and a mutation that hangs, whose pytest gets killed. After a SIGKILL
nothing of pytest runs, so each process watches its parent: `tests/die_with_parent.py`.
"""

import os
import signal
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

from tests import die_with_parent, mutation_support
from tests.deployment_helpers import ROOT, Deployment, wait_until

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


def test_a_pytest_killed_half_way_leaves_no_node(tmp_path):
    # No teardown, no conftest and no handler can run here: the nodes must notice by themselves.
    test, base = write_test(tmp_path, """
        def test_it():
            made = Deployment(BASE)
            made.start_all()
            time.sleep(300)
    """)
    process = subprocess.Popen(
        [sys.executable, "-m", "pytest", "-q", "-p", "tests.conftest", "-p", "no:cacheprovider", "--rootdir", str(test.parent), str(test)],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        assert wait_until(lambda: len(alive_under(base)) == 4, 60)
        process.send_signal(signal.SIGKILL)
        process.wait(timeout=10)
        assert gone(base), alive_under(base)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()

        for line in alive_under(base):
            os.kill(int(line.split()[0]), signal.SIGKILL)


def test_a_worker_of_the_tests_dies_with_pytest_too(tmp_path):
    # Not only nodes: these hold a store until somebody kills them.
    test, base = write_test(tmp_path, """
        from tests.test_quorum_byzantine import _spawn_worker

        def test_it():
            _spawn_worker("hold-node-halted", BASE / "votes.sqlite")
            print("UP", flush=True)
            time.sleep(300)
    """)
    pattern = f"quorum.*hold-node-halted .*{base}"
    process = subprocess.Popen(
        [sys.executable, "-m", "pytest", "-q", "-p", "tests.conftest", "-p", "no:cacheprovider", "--rootdir", str(test.parent), str(test)],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    def workers() -> list[str]:
        found = subprocess.run(["pgrep", "-af", pattern], capture_output=True, text=True).stdout
        return [line for line in found.splitlines() if "pgrep" not in line]

    try:
        assert wait_until(lambda: len(workers()) == 1, 60)
        process.send_signal(signal.SIGKILL)
        process.wait(timeout=10)
        assert wait_until(lambda: not workers(), 15), workers()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()

        for line in workers():
            os.kill(int(line.split()[0]), signal.SIGKILL)


SLEEPER = "import time\nprint('UP', flush=True)\ntime.sleep(120)\n"
PARENT = """
import subprocess, sys, os
child = subprocess.Popen([sys.executable, sys.argv[1], str(os.getpid()), sys.argv[2]], stdout=subprocess.PIPE, text=True)
assert child.stdout.readline().strip() == "UP"
print(child.pid, flush=True)
import time
time.sleep(120)
"""


def child_outlives_a_killed_parent(launcher, tmp_path) -> bool:
    sleeper = tmp_path / "sleeper.py"
    sleeper.write_text(SLEEPER)
    parent = subprocess.Popen(
        [sys.executable, "-c", PARENT, str(launcher), str(sleeper)],
        stdout=subprocess.PIPE,
        text=True,
    )
    pid = int(parent.stdout.readline())
    parent.kill()
    parent.wait(timeout=10)
    parent.stdout.close()

    def alive() -> bool:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False

    died = wait_until(lambda: not alive(), 5)

    if not died:
        os.kill(pid, signal.SIGKILL)

    return not died


def test_the_launcher_ends_a_process_whose_parent_was_killed(tmp_path):
    assert not child_outlives_a_killed_parent(Path(die_with_parent.__file__), tmp_path)


def test_a_launcher_that_does_not_watch_is_noticed(tmp_path):
    # The same file, with the watch taken out: the check above must see the child survive.
    source = Path(die_with_parent.__file__).read_text()
    watch = "    while os.getppid() == parent:\n        time.sleep(POLL_SECONDS)\n\n    os.kill(os.getpid(), signal.SIGKILL)\n"
    assert source.count(watch) == 1
    mutated = tmp_path / "die_with_parent.py"
    mutated.write_text(source.replace(watch, "    time.sleep(1000)\n"))
    assert child_outlives_a_killed_parent(mutated, tmp_path)


def test_a_node_outlives_the_thread_that_started_it(tmp_path):
    # What PR_SET_PDEATHSIG would get wrong: only the death of the process counts.
    (tmp_path / "made").mkdir()
    made = Deployment(tmp_path / "made")
    thread = threading.Thread(target=made.start, args=(0,))
    thread.start()
    thread.join()

    try:
        time.sleep(2 * die_with_parent.POLL_SECONDS + 0.5)
        assert made.processes[0].poll() is None
    finally:
        made.stop_all()


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
