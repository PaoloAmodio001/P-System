"""The tests of tests/test_peer_queue_and_fragments.py must be able to fail.

The process-free tests see each mutation. The test that closes a real epoch larger than a frame
stays out because it takes half a minute: "only the types of a closure" and the check on the size
are enough to detect its breakage, and it fails by itself on code without fragments.
"""

from pathlib import Path

import pytest

from tests.mutation_support import ROOT, run_tests_on

TESTS = [
    str(Path("tests") / "test_peer_queue_and_fragments.py"),
    "-k",
    "not epoch_larger",
]

FRAGMENTS = {
    "any type can be split": (
        "    if carries not in FRAGMENTABLE_TYPES or len(payload) > MAX_ASSEMBLED_SIZE:\n",
        "    if len(payload) > MAX_ASSEMBLED_SIZE:\n",
    ),
    "any size can be split": (
        "    if carries not in FRAGMENTABLE_TYPES or len(payload) > MAX_ASSEMBLED_SIZE:\n",
        "    if carries not in FRAGMENTABLE_TYPES:\n",
    ),
    "the limit itself refused": (
        "    if carries not in FRAGMENTABLE_TYPES or len(payload) > MAX_ASSEMBLED_SIZE:\n",
        "    if carries not in FRAGMENTABLE_TYPES or len(payload) >= MAX_ASSEMBLED_SIZE:\n",
    ),
    "fields not checked": (
        "        if fragment.keys() != _FRAGMENT_FIELDS:\n"
        "            raise ValueError(\"INVALID FRAGMENT\")\n",
        "        if not fragment.keys() >= _FRAGMENT_FIELDS:\n"
        "            raise ValueError(\"INVALID FRAGMENT\")\n",
    ),
    "carried type of another form": (
        "            type(fragment[\"carries\"]) is not str\n"
        "            or fragment[\"carries\"] not in FRAGMENTABLE_TYPES\n",
        "            fragment[\"carries\"] not in FRAGMENTABLE_TYPES\n",
    ),
    "carried type not checked": (
        "            or fragment[\"carries\"] not in FRAGMENTABLE_TYPES\n",
        "",
    ),
    "digest of another form": (
        "            or _DIGEST_PATTERN.fullmatch(digest) is None\n",
        "",
    ),
    "uppercase digest": (
        "_DIGEST_PATTERN = re.compile(r\"[0-9a-f]{64}\")\n",
        "_DIGEST_PATTERN = re.compile(r\"[0-9a-fA-F]{64}\")\n",
    ),
    "boolean index": (
        "            or type(index) is not int\n",
        "            or not isinstance(index, int)\n",
    ),
    "boolean total": (
        "            or type(total) is not int\n",
        "            or not isinstance(total, int)\n",
    ),
    "no limit on the pieces": (
        "            or not 0 <= index < total <= _MAX_FRAGMENTS\n",
        "            or not 0 <= index < total\n",
    ),
    "index beyond the total": (
        "            or not 0 <= index < total <= _MAX_FRAGMENTS\n",
        "            or not 0 <= index <= total <= _MAX_FRAGMENTS\n",
    ),
    "data of another type": (
        "            or type(fragment[\"data\"]) is not str\n",
        "",
    ),
    "pieces in any order": (
        "        if index != self._next:\n"
        "            raise ValueError(\"FRAGMENT OUT OF ORDER\")\n",
        "",
    ),
    "pieces of another message": (
        "        elif (digest, fragment[\"carries\"], total) != (self._id, self._carries, self._total):\n"
        "            raise ValueError(\"FRAGMENT OF ANOTHER MESSAGE\")\n",
        "",
    ),
    "lax base64": (
        "            piece = base64.b64decode(fragment[\"data\"], validate=True)\n",
        "            piece = base64.b64decode(fragment[\"data\"])\n",
    ),
    "piece of any size": (
        "        if not 0 < len(piece) <= FRAGMENT_DATA_SIZE:\n"
        "            raise ValueError(\"INVALID FRAGMENT\")\n",
        "",
    ),
    "digest not checked": (
        "        if hashlib.sha256(payload).hexdigest() != expected:\n"
        "            raise ValueError(\"FRAGMENTS DO NOT MATCH THEIR DIGEST\")\n",
        "",
    ),
    "assembler not reset": (
        "        expected = self._id\n"
        "        self._reset()\n",
        "        expected = self._id\n",
    ),
}

CONNECTION = {
    "large message not split": (
        "        if len(payload) <= SecureTransport.MAX_MESSAGE_SIZE:\n"
        "            return [SecureTransport.frame_of_payload(payload)]\n"
        "\n"
        "        return [\n"
        "            SecureTransport.frame_of_payload(SecureTransport.encode_payload(fragment))\n"
        "            for fragment in split_payload(message.get(\"type\"), payload)\n"
        "        ]\n",
        "        return [SecureTransport.frame_of_payload(payload)]\n",
    ),
    "no bound on the queue": (
        "            if self._queued_bytes + size > self.MAX_QUEUED_BYTES:\n"
        "                raise ConnectionError(\"PEER IS TOO FAR BEHIND\")\n",
        "",
    ),
    "queue never shrinks": (
        "                self._queued_bytes -= sum(len(frame) for frame in frames)\n",
        "",
    ),
    "enqueue waits for the peer": (
        "            self._queue.append(frames)\n"
        "            self._queued_bytes += size\n",
        "            self.send(message)\n"
        "            return\n",
    ),
    "last in first out": (
        "                frames = self._queue.popleft()\n",
        "                frames = self._queue.pop()\n",
    ),
    "a failed write says nothing": (
        "            except (ConnectionError, OSError, TimeoutError):\n"
        "                self._close_and_notify()\n"
        "                return\n"
        "\n"
        "            with self._queue_changed:\n",
        "            except (ConnectionError, OSError, TimeoutError):\n"
        "                return\n"
        "\n"
        "            with self._queue_changed:\n",
    ),
    "enqueue on a closed connection": (
        "        with self._queue_changed:\n"
        "            if self.connection is None:\n"
        "                raise ConnectionError(\"PEER NOT CONNECTED\")\n",
        "        with self._queue_changed:\n",
    ),
    "close leaves the queue": (
        "                self._queue.clear()\n"
        "                self._queued_bytes = 0\n",
        "",
    ),
    "close does not wake the writer": (
        "                self._queued_bytes = 0\n"
        "                self._queue_changed.notify_all()\n",
        "                self._queued_bytes = 0\n",
    ),
    "flush does not wait": (
        "                lambda: self._queued_bytes == 0 or self.connection is None,\n",
        "                lambda: True,\n",
    ),
    "message inside a fragmented one": (
        "        if self._assembler.in_progress:\n"
        "            raise ValueError(\"MESSAGE INSIDE A FRAGMENTED MESSAGE\")\n",
        "",
    ),
    "assembled payload not decoded as a message": (
        "            return None if payload is None else SecureTransport.decode_payload(payload)\n",
        "            import json\n"
        "            return None if payload is None else json.loads(payload)\n",
    ),
    "together does not stop at a piece": (
        "                if next_message is None:\n"
        "                    break\n",
        "                if next_message is None:\n"
        "                    continue\n",
    ),
}

NODE = {
    "broadcast waits for each peer": (
        "                    target.enqueue(message)\n",
        "                    target.send(message)\n",
    ),
}

CASES = [
    *(("network.fragments", "fragments.py", name, change) for name, change in FRAGMENTS.items()),
    *(("network.peer_connection", "peer_connection.py", name, change) for name, change in CONNECTION.items()),
    *(("network.node", "node.py", name, change) for name, change in NODE.items()),
]


def test_the_tests_pass_on_the_real_source():
    source = (ROOT / "network" / "fragments.py").read_text()
    result = run_tests_on("network.fragments", source, TESTS)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("case", CASES, ids=[case[2] for case in CASES])
def test_mutation_is_detected(case):
    module, file, _, (old, new) = case
    source = (ROOT / "network" / file).read_text()
    assert source.count(old) == 1
    result = run_tests_on(module, source.replace(old, new), TESTS)
    assert result.returncode == 1, result.stdout + result.stderr
