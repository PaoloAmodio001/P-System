"""Differential test B must be able to fail.

Each mutation breaks one rule outside the replica, in network/quorum.py or network/node.py,
and the comparison with runNode must report a divergence. Only that counts: a crash, or the
floor on what a corpus exercises, is not a detection. One seed, stopping at the first
difference, so this is fast unless a mutation survives.

The rules of the replica itself are for tests/test_quorum_differential_mutations.py.

Not here, because this comparison cannot see them, and each has a mutation elsewhere: trying
the buffer again on a repeated certificate, which matters only after a failed write
(test_quorum_driver_mutations.py), and the replica refusing to execute after a halt, since
the driver stops first (test_quorum_halt_mutations.py).
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
QUORUM = (ROOT / "network" / "quorum.py").read_text()
NODE = (ROOT / "network" / "node.py").read_text()

# network.quorum comes first and network.node after, because node.py takes its classes
# from there when it is imported.
RUNNER = """
import sys

import network.quorum

try:
    exec(compile(sys.argv[1], "network/quorum.py", "exec"), network.quorum.__dict__)
    import network.node
    exec(compile(sys.argv[2], "network/node.py", "exec"), network.node.__dict__)
except Exception:
    # Python exits with 1 on an uncaught exception, the same as a failing test.
    sys.exit(3)

import pytest

sys.exit(pytest.main(sys.argv[3:]))
"""

TESTS = [
    "tests/test_quorum_differential_node.py",
    "-q",
    "-x",
    "--no-header",
    "-p",
    "no:cacheprovider",
]

IN_QUORUM = {
    "signature of a request not checked": (
        "            and signed.verify()\n",
        "",
    ),
    "sender not tied to the signer": (
        "            and signed.identity_id == signed.transfer.sender\n",
        "",
    ),
    "buffer tried only once": (
        "                    del self._buffer[event_id]\n"
        "                    progress = True\n",
        "                    del self._buffer[event_id]\n",
    ),
    "buffer tried in another order": (
        "            for event_id in sorted(self._buffer):\n",
        "            for event_id in sorted(self._buffer, reverse=True):\n",
    ),
    "invalid certificate accepted": (
        "        if not self.halted and self.replica.certificate_is_valid(certificate):\n",
        "        if not self.halted:\n",
    ),
    "invalid certificate halts the node": (
        "        if not self.halted and self.replica.certificate_is_valid(certificate):\n"
        "            self._accept(certificate)\n",
        "        if not self.halted and self.replica.certificate_is_valid(certificate):\n"
        "            self._accept(certificate)\n"
        "        elif not self.halted:\n"
        "            known = self._known.get(\n"
        "                (certificate.event.sender, certificate.event.nonce)\n"
        "            )\n"
        "            if known is not None and"
        " known.event.canonical() != certificate.event.canonical():\n"
        "                self.replica._store._connection.execute(\n"
        '                    "INSERT OR IGNORE INTO halt VALUES (1, ?, ?, ?, ?, 0, 0)",\n'
        "                    (known.event.canonical().decode(),\n"
        "                     _encode_signatures(known),\n"
        "                     certificate.event.canonical().decode(),\n"
        "                     _encode_signatures(certificate)),\n"
        "                )\n",
    ),
    "conflict does not halt": (
        "            self.replica.record_halt(known, certificate)\n"
        "            self._buffer.clear()\n"
        "            self._aggregating.clear()\n"
        "            return\n",
        "            self._retry_buffer()\n"
        "            return\n",
    ),
    "halt on the same event": (
        "        if known is not None and known.event.canonical() != event.canonical():\n",
        "        if known is not None:\n",
    ),
    "conflict with the buffer missed": (
        "            self._known[key] = certificate\n",
        "            if self.replica.state.nonce(event.sender) > event.nonce:\n"
        "                self._known[key] = certificate\n",
    ),
    "log forgotten for conflicts after a restart": (
        "            for certificate in replica.log\n",
        "            for certificate in []\n",
    ),
    "vote given after a halt": (
        "                if self._is_halted():\n"
        "                    return False\n"
        "\n",
        "",
    ),
    "store forgets a halt": (
        '            self._connection.execute("SELECT 1 FROM halt").fetchone() is not None\n',
        "            False\n",
    ),
    "vote not written to disk": (
        "        if not self._store.record_vote(event, signed):\n"
        "            return None\n",
        "",
    ),
    "bad vote counted": (
        "        if not vote.verify(self.committee, event):\n",
        "        if False:\n",
    ),
    "votes counted for an event not submitted here": (
        "        aggregating = self._aggregating.get(event.canonical())\n",
        "        aggregating = self._aggregating.setdefault(\n"
        "            event.canonical(), (event, {})\n"
        "        )\n",
    ),
    "certificate made below the quorum": (
        "        if len(votes) < self.committee.quorum:\n",
        "        if len(votes) < self.committee.quorum - 1:\n",
    ),
    "new certificate not executed here": (
        "        self._accept(certificate)\n"
        "        return certificate\n",
        "        return certificate\n",
    ),
    "submit asks even when its own vote is refused": (
        "        if vote is None:\n"
        "            return _NOTHING\n"
        "\n"
        "        _, votes = self._aggregating",
        "        if vote is None:\n"
        "            return DriverOutput(broadcasts=(encode_vote_request(signed),))\n"
        "\n"
        "        _, votes = self._aggregating",
    ),
}

IN_NODE = {
    "evidence votes": (
        "                self._quorum.driver.record_evidence(event)\n",
        "                self._quorum.driver.record_evidence(event)\n"
        "                self._quorum.replica.handle_vote_request(event.transfer)\n",
    ),
    "evidence executes": (
        "                self._quorum.driver.record_evidence(event)\n",
        "                self._quorum.driver.record_evidence(event)\n"
        "                if self._quorum.replica._is_ready(event.transfer) and"
        " self._quorum.replica._is_executable(event.transfer) and"
        " self._quorum.replica._is_fresh(event.transfer):\n"
        "                    self._quorum.replica._execute(\n"
        "                        type('C', (), {'event': event.transfer})()\n"
        "                    )\n",
    ),
    "state not restored at a restart": (
        "            self._sync_interval = quorum.sync_interval\n"
        "            self._publish_quorum_state()\n",
        "            self._sync_interval = quorum.sync_interval\n",
    ),
    "public state not published after a message": (
        "            finally:\n"
        "                self._publish_quorum_state()\n"
        "\n"
        "        self._send_quorum_output(output, connection)\n",
        "            finally:\n"
        "                pass\n"
        "\n"
        "        self._send_quorum_output(output, connection)\n",
    ),
    "public state not published after submit": (
        "            finally:\n"
        "                self._publish_quorum_state()\n"
        "\n"
        "        self._send_quorum_output(output, None)\n",
        "            finally:\n"
        "                pass\n"
        "\n"
        "        self._send_quorum_output(output, None)\n",
    ),
    "public events drift from the log": (
        "        self.events.extend(added)\n",
        "        self.events.extend(added)\n"
        "        self.events.sort(key=lambda e: e.event_id())\n",
    ),
    "halt does not reach the status": (
        "        known = list(self.events) + self._quorum_halt_events\n",
        "        known = list(self.events)\n",
    ),
    "replies not sent": (
        "                self._send_quorum_reply(connection, message)\n",
        "                pass\n",
    ),
    "broadcasts not sent": (
        "                    target.enqueue(message)\n",
        "                    pass\n",
    ),
    "quorum messages take the old way": (
        "        if self._quorum is not None and message_type in QUORUM_MESSAGE_TYPES:\n",
        "        if False:\n",
    ),
}


def _run(quorum: str, node: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", RUNNER, quorum, node, *TESTS],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
        env={**os.environ, "PSYSTEM_DIFF_SEEDS": "1"},
    )


def test_the_comparison_passes_on_the_real_source():
    result = _run(QUORUM, NODE)
    assert result.returncode == 0, result.stdout + result.stderr


def _assert_diverges(result: subprocess.CompletedProcess) -> None:
    # Only a reported divergence counts. It has to be in the failure message, because
    # return code 1 would also come from a crash or from the floor on coverage.
    assert result.returncode == 1, result.stdout + result.stderr
    assert "diverges. Minimal case" in result.stdout, result.stdout[-2000:]


@pytest.mark.parametrize("name", IN_QUORUM)
def test_mutation_in_quorum_is_detected(name):
    old, new = IN_QUORUM[name]
    assert QUORUM.count(old) == 1, name
    _assert_diverges(_run(QUORUM.replace(old, new), NODE))


@pytest.mark.parametrize("name", IN_NODE)
def test_mutation_in_node_is_detected(name):
    old, new = IN_NODE[name]
    assert NODE.count(old) == 1, name
    _assert_diverges(_run(QUORUM, NODE.replace(old, new)))
