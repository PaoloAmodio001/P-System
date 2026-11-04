"""The tests of synchronization must be able to fail.

Rules of the driver and of the decoder against tests/test_quorum_sync.py. What the node adds
(asking on connecting, asking at intervals) against tests/test_quorum_differential_network.py,
on the scenarios that need it. Real TLS is what those scenarios are about, so they stay in.

Not here on purpose: the length of an entry of the frontier. Without that check the unpacking
raises ValueError anyway, which is the same answer.
"""

from pathlib import Path

import pytest

from tests.mutation_support import ROOT, run_tests_on

SYNC_TESTS = [str(Path("tests") / "test_quorum_sync.py")]
NETWORK = str(Path("tests") / "test_quorum_differential_network.py")

SOURCES = {
    "network.quorum": (ROOT / "network" / "quorum.py").read_text(),
    "network.message": (ROOT / "network" / "message.py").read_text(),
    "network.node": (ROOT / "network" / "node.py").read_text(),
}

DRIVER = {
    "request not handled": (
        "        if message_type == \"CERTIFICATE_SYNC_REQUEST\":\n",
        "        if message_type == \"CERTIFICATE_SYNC_REQUEST\" and False:\n",
    ),
    "batch not handled": (
        "        if message_type == \"CERTIFICATE_SYNC\":\n",
        "        if message_type == \"CERTIFICATE_SYNC\" and False:\n",
    ),
    "a halted node keeps asking": (
        "        if self.halted:\n"
        "            return None\n"
        "\n"
        "        return encode_certificate_sync_request(self._frontier())\n",
        "        return encode_certificate_sync_request(self._frontier())\n",
    ),
    "frontier ignores the buffer": (
        "            while (sender, nonce) in self._known:\n"
        "                nonce += 1\n",
        "",
    ),
    "frontier jumps over a hole": (
        "            while (sender, nonce) in self._known:\n"
        "                nonce += 1\n",
        "            nonce = max(k[1] + 1 for k in self._known if k[0] == sender)\n",
    ),
    "frontier without a limit": (
        "        return dict(sorted(frontier.items())[:SYNC_MAX_FRONTIER_SENDERS])\n",
        "        return frontier\n",
    ),
    "index misses later events": (
        "        self._indexed = len(log)\n",
        "        self._indexed = 10**9\n",
    ),
    "answer ignores the frontier": (
        "            start = max(0, frontier.get(sender, 0) - certificates[0].event.nonce)\n",
        "            start = 0\n",
    ),
    "answer assumes nonces start at zero": (
        "            start = max(0, frontier.get(sender, 0) - certificates[0].event.nonce)\n",
        "            start = frontier.get(sender, 0)\n",
    ),
    "answer without a limit": (
        "                if batch and size > SYNC_BATCH_BYTES:\n"
        "                    return DriverOutput(replies=(encode_certificate_sync(batch),))\n",
        "",
    ),
    "limit can give an empty batch": (
        "                if batch and size > SYNC_BATCH_BYTES:\n",
        "                if size > SYNC_BATCH_BYTES:\n",
    ),
    "empty answer sent": (
        "        if not batch:\n"
        "            return _NOTHING\n",
        "",
    ),
    "batch runs after a halt": (
        "            if self.halted:\n"
        "                return _NOTHING\n"
        "\n"
        "            event = certificate.event\n",
        "            event = certificate.event\n",
    ),
    "known certificates checked again": (
        "            if known is not None and known.event.canonical() == event.canonical():\n"
        "                continue\n",
        "",
    ),
    "a conflict is taken for a known certificate": (
        "            if known is not None and known.event.canonical() == event.canonical():\n"
        "                continue\n",
        "            if known is not None:\n"
        "                continue\n",
    ),
    "batch not checked": (
        "            if not certificate.verify(self.committee):\n"
        "                return _NOTHING\n"
        "\n"
        "            self._accept(certificate)\n"
        "            learned = True\n",
        "            self._accept(certificate)\n"
        "            learned = True\n",
    ),
    "bad certificate only skipped": (
        "            if not certificate.verify(self.committee):\n"
        "                return _NOTHING\n"
        "\n"
        "            self._accept(certificate)\n"
        "            learned = True\n",
        "            if not certificate.verify(self.committee):\n"
        "                continue\n"
        "\n"
        "            self._accept(certificate)\n"
        "            learned = True\n",
    ),
    "always asks again": (
        "        request = self.sync_request() if learned else None\n",
        "        request = self.sync_request()\n",
    ),
    "never asks again": (
        "        request = self.sync_request() if learned else None\n",
        "        request = None\n",
    ),
}

DECODER = {
    "frontier that is not a list": (
        "    if type(data[\"frontier\"]) is not list:\n"
        "        raise ValueError(\"INVALID QUORUM MESSAGE\")\n",
        "",
    ),
    "entry that is not a list": (
        "        if type(entry) is not list or len(entry) != 2:\n",
        "        if len(entry) != 2:\n",
    ),
    "entry not checked as an event": (
        "        if not is_well_formed_event(Transfer(sender, sender, 0, nonce)):\n"
        "            raise ValueError(\"INVALID QUORUM MESSAGE\")\n",
        "",
    ),
    "any order": (
        "        if previous is not None and sender <= previous:\n"
        "            raise ValueError(\"INVALID QUORUM MESSAGE\")\n",
        "",
    ),
    "repeated sender": (
        "        if previous is not None and sender <= previous:\n",
        "        if previous is not None and sender < previous:\n",
    ),
    "encoded unsorted": (
        "            for sender in sorted(frontier)\n",
        "            for sender in frontier\n",
    ),
}

NODE = {
    "no request on connecting": (
        "        thread.start()\n"
        "        self._request_certificates(connection)\n",
        "        thread.start()\n",
    ),
    "no request when a peer connects to this node": (
        "    def _request_certificates(self, connection) -> None:\n"
        "        \"\"\"Ask a peer for what this node lacks. In quorum mode only.\"\"\"\n"
        "        if self._quorum is None:\n",
        "    def _request_certificates(self, connection) -> None:\n"
        "        \"\"\"Ask a peer for what this node lacks. In quorum mode only.\"\"\"\n"
        "        if self._quorum is None or not connection.initiated_locally:\n",
    ),
    "no request at intervals": (
        "            for connection in targets:\n"
        "                self._request_certificates(connection)\n",
        "",
    ),
    "a blocked send stops the broadcast": (
        "                except (ConnectionError, OSError, TimeoutError):\n"
        "                    self._disconnect_peer_connection(node_id, target)\n",
        "                except (ConnectionError, OSError, TimeoutError):\n"
        "                    self._disconnect_peer_connection(node_id, target)\n"
        "                    return\n",
    ),
}


def test_the_tests_pass_on_the_real_source():
    result = run_tests_on("network.quorum", SOURCES["network.quorum"], SYNC_TESTS)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("name", DRIVER)
def test_mutation_in_the_driver_is_detected(name):
    old, new = DRIVER[name]
    source = SOURCES["network.quorum"]
    assert source.count(old) == 1, name
    result = run_tests_on("network.quorum", source.replace(old, new), SYNC_TESTS)
    assert result.returncode == 1, result.stdout + result.stderr


@pytest.mark.parametrize("name", DECODER)
def test_mutation_in_the_decoder_is_detected(name):
    old, new = DECODER[name]
    source = SOURCES["network.message"]
    assert source.count(old) == 1, name
    result = run_tests_on("network.message", source.replace(old, new), SYNC_TESTS)
    assert result.returncode == 1, result.stdout + result.stderr


@pytest.mark.parametrize("name", NODE)
def test_mutation_in_the_node_is_detected(name):
    old, new = NODE[name]
    source = SOURCES["network.node"]
    assert source.count(old) == 1, name
    result = run_tests_on("network.node", source.replace(old, new), [NETWORK])
    assert result.returncode == 1, result.stdout + result.stderr
