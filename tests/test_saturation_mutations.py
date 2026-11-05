"""The tests of tests/test_saturation.py must be able to fail.

Not here on purpose:
- the checks that hold a bad signature on each kind of message beyond the three in the test: each is the
  same line, and their cost is a wait, not a change of result.
- the order of the two checks in `submit`: it only costs a signature.
"""

from pathlib import Path

import pytest

from tests.mutation_support import ROOT, run_tests_on

TESTS = [str(Path("tests") / "test_saturation.py")]

MUTATIONS = {
    "network.node_server": {
        "the new one is refused and not the oldest": (
            "        self._pending.pop(oldest, None)\n        self._addresses.pop(oldest, None)\n        self._shut_down(oldest)\n",
            "        raise OSError\n",
        ),
        "no limit for each address": (
            "        if len(same) >= self.MAX_PENDING_PER_ADDRESS:\n            oldest = same[0]\n        elif len(self._pending)",
            "        if len(self._pending)",
        ),
        "no limit for all": (
            "        elif len(self._pending) >= self.MAX_PENDING_HANDSHAKES:\n            oldest = next(iter(self._pending))\n",
            "",
        ),
        "the oldest stays and is only forgotten": (
            "        self._addresses.pop(oldest, None)\n        self._shut_down(oldest)\n",
            "        self._addresses.pop(oldest, None)\n",
        ),
    },
    "network.peer_connection": {
        "a debt waits all at once": (
            "            self._sleep(min(self.MAX_WAIT, -self._tokens / self.rate))\n",
            "            self._sleep(-self._tokens / self.rate)\n",
        ),
        "a charge is forgotten": (
            "        self._pacer.take(tokens)\n",
            "        pass\n",
        ),
        "enqueue returns nothing": (
            "        return size\n\n    def _write_queued",
            "        return 0\n\n    def _write_queued",
        ),
    },
    "network.node": {
        "the cost is not charged": (
            "        if connection is not None and output.cost:\n            connection.charge(output.cost)\n",
            "",
        ),
        "an answer is free": (
            "            connection.charge(connection.enqueue(message) // REPLY_BYTES_PER_TOKEN)\n",
            "            connection.enqueue(message)\n",
        ),
        "the evidence is copied": (
            "        self.signed_events.update(driver.new_signed_events())\n",
            "        self.signed_events = {**self.signed_events, **driver.new_signed_events()}\n",
        ),
        "a new driver keeps the old evidence": (
            "            self._published_driver = driver\n            self.signed_events = {}\n",
            "            self._published_driver = driver\n",
        ),
    },
    "network.quorum": {
        "a bad vote request is free": (
            "        if not self._is_authorized(signed):\n            self._cost += BAD_SIGNATURE_COST\n            return _NOTHING\n",
            "        if not self._is_authorized(signed):\n            return _NOTHING\n",
        ),
        "a bad certificate is free": (
            "        else:\n            self._cost += BAD_SIGNATURE_COST\n\n        return _NOTHING\n",
            "\n        return _NOTHING\n",
        ),
        "a bad batch is free": (
            "            if not self.replica.certificate_is_valid(certificate):\n                self._cost += BAD_SIGNATURE_COST\n                return _NOTHING\n",
            "            if not self.replica.certificate_is_valid(certificate):\n                return _NOTHING\n",
        ),
        "the cost is carried over": (
            "        self._cost = 0\n        output = self._dispatch(message)\n",
            "        output = self._dispatch(message)\n",
        ),
        "the cost is not reported": (
            "        if self._cost:\n            return replace(output, cost=self._cost)\n\n",
            "",
        ),
        "a group forgets the cost": (
            "                cost += output.cost\n",
            "",
        ),
        "the signature comes first": (
            "        if not self._is_admitted(signed.transfer):\n            return _NOTHING\n\n        if not self._is_authorized(signed):\n            self._cost += BAD_SIGNATURE_COST\n            return _NOTHING\n",
            "        if not self._is_authorized(signed):\n            self._cost += BAD_SIGNATURE_COST\n            return _NOTHING\n\n        if not self._is_admitted(signed.transfer):\n            return _NOTHING\n",
        ),
        "the signature comes first when submitting": (
            "        if self.halted or not self._is_admitted(signed.transfer):\n            return _NOTHING\n\n        if not self._is_authorized(signed):\n            return _NOTHING\n",
            "        if self.halted or not self._is_authorized(signed):\n            return _NOTHING\n\n        if not self._is_admitted(signed.transfer):\n            return _NOTHING\n",
        ),
        "no limit for the buffer": (
            "        return len(self._buffer) < self.max_buffered\n",
            "        return True\n",
        ),
        "no window for the buffer": (
            "        if self.max_nonce_ahead is not None and event.nonce > expected + self.max_nonce_ahead:\n            return False\n\n",
            "",
        ),
        "the next nonce waits for room": (
            "        if event.nonce <= expected:\n            return True\n\n",
            "",
        ),
        "one left out stays known": (
            "            if not self._has_room_for(event):\n                self.certificates_left_out += 1\n                return False\n\n            event_id = event.event_id()\n            self._known[key] = certificate\n",
            "            self._known[key] = certificate\n            if not self._has_room_for(event):\n                self.certificates_left_out += 1\n                return False\n\n            event_id = event.event_id()\n",
        ),
        "one left out is not counted": (
            "                self.certificates_left_out += 1\n",
            "",
        ),
        "one left out counts as learned": (
            "            if self._accept(certificate):\n                learned = True\n",
            "            self._accept(certificate)\n            learned = True\n",
        ),
        "every certificate is tried": (
            "            ready = [\n                nonces[state.nonce(sender)]\n                for sender, nonces in self._waiting.items()\n                if state.nonce(sender) in nonces\n            ]\n",
            "            ready = list(self._buffer)\n",
        ),
        "tried only once": (
            "                    self._no_longer_waiting(event_id)\n                    progress = True\n",
            "                    self._no_longer_waiting(event_id)\n",
        ),
        "a halt leaves what waits": (
            "            self._buffer.clear()\n            self._waiting.clear()\n",
            "            self._buffer.clear()\n",
        ),
        "what ran stays waiting": (
            "        del nonces[event.nonce]\n\n        if not nonces:\n            del self._waiting[event.sender]\n",
            "        del nonces[event.nonce]\n",
        ),
        "no limit on events being collected": (
            "            and len(self._aggregating) >= self.max_aggregating\n",
            "            and False\n",
        ),
        "an event being collected is refused": (
            "            event.canonical() not in self._aggregating\n            and len(self._aggregating) >= self.max_aggregating\n",
            "            len(self._aggregating) >= self.max_aggregating\n",
        ),
        "evidence published again and again": (
            "        self._unpublished_signed = []\n",
            "",
        ),
        "a proof published again and again": (
            "        self._unpublished_proofs = []\n        return new\n",
            "        return new\n",
        ),
    },
}

ALL = [(module, name) for module, table in MUTATIONS.items() for name in table]


def source_of(module: str) -> str:
    return (ROOT / (module.replace(".", "/") + ".py")).read_text()


@pytest.mark.parametrize("module", MUTATIONS)
def test_the_tests_pass_on_the_real_source(module):
    result = run_tests_on(module, source_of(module), TESTS)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("module,name", ALL)
def test_mutation_is_detected(module, name):
    old, new = MUTATIONS[module][name]
    source = source_of(module)
    assert source.count(old) == 1, name
    result = run_tests_on(module, source.replace(old, new), TESTS)
    assert result.returncode == 1, result.stdout + result.stderr
