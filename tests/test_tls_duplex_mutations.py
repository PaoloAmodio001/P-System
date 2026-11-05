"""The tests of tests/test_tls_duplex.py must be able to fail.

The tests that start a process import the real module, so they stay out here. They are also
the ones that depend on timing: the lock and the wrapping are checked by tests that do not.

Not here on purpose: the check on a closed stream in `sendall`. Without it the send on the
closed socket raises OSError, so a writer stops anyway and only the type of error changes.
"""

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
    "no lock on the calls": (
        "        self._io_lock = threading.Lock()\n",
        "        import contextlib\n"
        "        self._io_lock = contextlib.nullcontext()\n",
    ),
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
        "        while True:\n"
        "            self._check_open()\n"
        "\n"
        "            try:\n"
        "                with self._io_lock:\n"
        "                    self._check_open()\n"
        "                    return self._sock.recv(size)\n",
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


def test_without_the_wrapping_a_tls_socket_is_used_bare():
    source = (ROOT / "network" / "peer_connection.py").read_text()
    old = "    if isinstance(connection, ssl.SSLSocket):\n"
    assert source.count(old) == 1
    result = run_tests_on(
        "network.peer_connection",
        source.replace(old, "    if False:\n"),
        TESTS,
    )
    assert result.returncode == 1, result.stdout + result.stderr


def test_the_tests_pass_on_the_real_source():
    result = run_tests_on(MODULE, SOURCE, TESTS)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("name", MUTATIONS)
def test_mutation_is_detected(name):
    old, new = MUTATIONS[name]
    assert SOURCE.count(old) == 1, name
    result = run_tests_on(MODULE, SOURCE.replace(old, new), TESTS)
    assert result.returncode == 1, result.stdout + result.stderr
