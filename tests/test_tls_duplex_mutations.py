"""The tests of tests/test_tls_duplex.py must be able to fail.

The tests that start a process import the real module, so they stay out here. The removal of
the lock and of the wrapping is checked by running the worker on the mutated source: see
test_without_the_wrapping_the_old_failure_comes_back.

Not here on purpose: the check on a closed stream in `sendall`. Without it the send on the
closed socket raises OSError, so a writer stops anyway and only the type of error changes.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from tests.mutation_support import ROOT, run_tests_on

MODULE = "network.secure_transport"
SOURCE = (ROOT / "network" / "secure_transport.py").read_text()
TESTS = [
    str(Path("tests") / "test_tls_duplex.py"),
    "-k",
    "not reader_and_writer_on_one_tls_connection",
]

MUTATIONS = {
    "no deadline on a send": (
        "                if remaining <= 0:\n"
        "                    raise TimeoutError(\"PEER IS NOT READING\") from error\n",
        "                remaining = 1.0\n",
    ),
    "deadline does not grow with the frame": (
        "            + len(frame) / self.SEND_BYTES_PER_SECOND\n",
        "",
    ),
    "close does not stop a reader": (
        "    def recv(self, size: int) -> bytes:\n"
        "        while True:\n"
        "            self._check_open()\n"
        "\n"
        "            try:\n"
        "                with self._io_lock:\n"
        "                    self._check_open()\n"
        "                    return self._sock.recv(size)\n",
        "    def recv(self, size: int) -> bytes:\n"
        "        while True:\n"
        "            try:\n"
        "                with self._io_lock:\n"
        "                    return self._sock.recv(size)\n",
    ),
    "send loses the rest of a long frame": (
        "                    offset += self._sock.send(chunk)\n",
        "                    offset += self._sock.send(chunk) * 2\n",
    ),
}


def test_the_tests_pass_on_the_real_source():
    result = run_tests_on(MODULE, SOURCE, TESTS)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("name", MUTATIONS)
def test_mutation_is_detected(name):
    old, new = MUTATIONS[name]
    assert SOURCE.count(old) == 1, name
    result = run_tests_on(MODULE, SOURCE.replace(old, new), TESTS)
    assert result.returncode == 1, result.stdout + result.stderr


def _worker_failures(source: str, module: str, runs: int) -> int:
    runner = (
        "import importlib, runpy, sys\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        f"module = importlib.import_module({module!r})\n"
        "exec(compile(sys.argv[1], module.__file__, 'exec'), module.__dict__)\n"
        "worker = sys.argv[2]\n"
        "sys.argv = [worker, '3000', '64']\n"
        "runpy.run_path(worker, run_name='__main__')\n"
    )
    failures = 0

    for _ in range(runs):
        try:
            result = subprocess.run(
                [sys.executable, "-c", runner, source, str(ROOT / "tests" / "tls_duplex_worker.py")],
                capture_output=True,
                timeout=40,
            )
            failures += result.returncode != 0
        except subprocess.TimeoutExpired:
            failures += 1

    return failures


def test_without_the_wrapping_the_old_failure_comes_back():
    source = (ROOT / "network" / "peer_connection.py").read_text()
    old = "    if isinstance(connection, ssl.SSLSocket):\n"
    assert source.count(old) == 1
    mutated = source.replace(old, "    if False:\n")
    # About a third of the runs fail: 25 runs miss it about once in 10^4.
    assert _worker_failures(mutated, "network.peer_connection", 25) > 0


def test_without_the_lock_on_ssl_calls_the_old_failure_comes_back():
    old = "        self._io_lock = threading.Lock()\n"
    assert SOURCE.count(old) == 1
    mutated = SOURCE.replace(
        old,
        "        import contextlib\n"
        "        self._io_lock = contextlib.nullcontext()\n",
    )
    assert _worker_failures(mutated, "network.secure_transport", 25) > 0
