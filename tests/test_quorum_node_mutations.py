"""The tests of Node in quorum mode must be able to fail.

Each mutation removes one rule from the source of network/node.py, and
tests/test_quorum_node.py must notice. Same method as test_quorum_halt_mutations.py,
on the other module. More mutations come with the differential test on Node.
"""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SOURCE = (ROOT / "network" / "node.py").read_text()

RUNNER = """
import sys

import network.node
import pytest

try:
    exec(compile(sys.argv[1], "network/node.py", "exec"), network.node.__dict__)
except Exception:
    # Python exits with 1 on an uncaught exception, the same as a failing test.
    sys.exit(3)

sys.exit(pytest.main(sys.argv[2:]))
"""

TESTS = [
    "tests/test_quorum_node.py",
    "-q",
    "-x",
    "--no-header",
    "-p",
    "no:cacheprovider",
]

MUTATIONS = {
    "state not restored at a restart": (
        "        self._sync_interval = quorum.sync_interval\n"
        "        self._publish_quorum_state()\n",
        "        self._sync_interval = quorum.sync_interval\n",
    ),
    "public state not a copy": (
        "        self.state = replica.state.copy()\n",
        "        self.state = replica.state\n",
    ),
    "public events shared with the replica": (
        "        self.local_events.extend(added)\n",
        "        self.local_events = self._quorum.replica.log\n",
    ),
    "evidence not published": (
        "        self.signed_events.update(driver.new_signed_events())\n",
        "",
    ),
    "equivocation not published": (
        "        self.equivocations = equivocations\n",
        "",
    ),
    "stop does not free the store": (
        "        with self._state_lock:\n"
        "            self._quorum.close()\n",
        "        pass\n",
    ),
    "stop does not wait for a message": (
        "        with self._state_lock:\n"
        "            self._quorum.close()\n",
        "        self._quorum.close()\n",
    ),
    "stopped node starts again": (
        '            raise RuntimeError("QUORUM NODE IS CLOSED: CREATE A NEW NODE")\n',
        "            pass\n",
    ),
    "evidence dropped": (
        "            self._quorum.driver.record_evidence(event)\n",
        "",
    ),
    "submit without the lock": (
        "        with self._state_lock:\n"
        "            try:\n"
        "                output = self._quorum.driver.submit(event)\n",
        "        if True:\n"
        "            try:\n"
        "                output = self._quorum.driver.submit(event)\n",
    ),
    "message without the lock": (
        "        with self._state_lock:\n"
        "            if self._quorum.closed:\n"
        "                return\n"
        "\n"
        "            # In finally:",
        "        if True:\n"
        "            if self._quorum.closed:\n"
        "                return\n"
        "\n"
        "            # In finally:",
    ),
    "quorum messages not dispatched": (
        "        if message.get(\"type\") in QUORUM_MESSAGE_TYPES:\n"
        "            self._handle_quorum_message(message, connection)\n",
        "        if False:\n"
        "            self._handle_quorum_message(message, connection)\n",
    ),
    "message handled after stop": (
        "            if self._quorum.closed:\n"
        "                return\n"
        "\n"
        "            # In finally:",
        "            # In finally:",
    ),
    "state not published when a write fails": (
        "            try:\n"
        "                output = self._quorum.driver.handle_message(message)\n"
        "            finally:\n"
        "                self._publish_quorum_state()\n",
        "            output = self._quorum.driver.handle_message(message)\n"
        "            self._publish_quorum_state()\n",
    ),
    "state not published after a message": (
        "            finally:\n"
        "                self._publish_quorum_state()\n"
        "\n"
        "        self._send_quorum_output(output, connection)\n",
        "            finally:\n"
        "                pass\n"
        "\n"
        "        self._send_quorum_output(output, connection)\n",
    ),
    "send with the lock held, message": (
        "            finally:\n"
        "                self._publish_quorum_state()\n"
        "\n"
        "        self._send_quorum_output(output, connection)\n",
        "            finally:\n"
        "                self._publish_quorum_state()\n"
        "\n"
        "            self._send_quorum_output(output, connection)\n",
    ),
    "send with the lock held, submit": (
        "            finally:\n"
        "                self._publish_quorum_state()\n"
        "\n"
        "        self._send_quorum_output(output, None)\n",
        "            finally:\n"
        "                self._publish_quorum_state()\n"
        "\n"
        "            self._send_quorum_output(output, None)\n",
    ),
    "replies not sent": (
        "                self._send_quorum_reply(connection, message)\n",
        "                pass\n",
    ),
    "broadcasts not sent": (
        "                    target.enqueue(message)\n",
        "                    pass\n",
    ),
    "failed broadcast stops the others": (
        "                    target.enqueue(message)\n"
        "                except (ConnectionError, OSError, TimeoutError):\n"
        "                    self._disconnect_peer_connection(node_id, target)\n",
        "                    target.enqueue(message)\n"
        "                except ZeroDivisionError:\n"
        "                    self._disconnect_peer_connection(node_id, target)\n",
    ),
    "failed reply raises": (
        "            connection.charge(connection.enqueue(message) // REPLY_BYTES_PER_TOKEN)\n"
        "        except (ConnectionError, OSError, TimeoutError):\n"
        "            self._peer_disconnected(connection)\n"
        "            connection.close()\n",
        "            connection.charge(connection.enqueue(message) // REPLY_BYTES_PER_TOKEN)\n"
        "        except ZeroDivisionError:\n"
        "            self._peer_disconnected(connection)\n"
        "            connection.close()\n",
    ),
    "failed reply keeps the connection": (
        "            self._peer_disconnected(connection)\n"
        "            connection.close()\n",
        "            pass\n",
    ),
    "halt does not reach the status": (
        "            return bool(self._quorum_halt_events)\n",
        "            return False\n",
    ),
    "halt not read": (
        "            proof = replica.halt_proof()\n",
        "            proof = None\n",
    ),
    "status needs an open store": (
        "        if not self._quorum.closed:\n"
        "            proof = replica.halt_proof()\n",
        "        if True:\n"
        "            proof = replica.halt_proof()\n",
    ),
}


def _run(source: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", RUNNER, source, *TESTS],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_the_tests_pass_on_the_real_source():
    result = _run(SOURCE)
    assert result.returncode == 0, result.stdout


@pytest.mark.parametrize("name", MUTATIONS)
def test_mutation_is_detected(name):
    old, new = MUTATIONS[name]
    assert SOURCE.count(old) == 1, name

    result = _run(SOURCE.replace(old, new))

    assert result.returncode == 1, result.stdout + result.stderr
