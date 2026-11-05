"""The tests of tests/test_quorum_epoch_retry.py must be able to fail."""

from pathlib import Path

import pytest

from tests.mutation_support import ROOT, run_tests_on

MODULE = "network.quorum"
SOURCE = (ROOT / "network" / "quorum.py").read_text()
TESTS = [str(Path("tests") / "test_quorum_epoch_retry.py")]

MUTATIONS = {
    "a proposer ignores its own vote": (
        "        if voted is not None:\n"
        "            broadcasts.extend(self._adopt(voted).broadcasts)\n"
        "        else:\n"
        "            broadcasts.extend(self._closure_if_reported().broadcasts)\n",
        "        broadcasts.extend(self._closure_if_reported().broadcasts)\n",
    ),
    "a vote for another order counts": (
        "        if voted is None or voted.change.change_id != change.change_id:\n"
        "            return None\n"
        "\n"
        "        return voted\n",
        "        return voted\n",
    ),
    "a member keeps quiet about its vote on a new order": (
        "        if voted is not None:\n"
        "            replies.append(encode_closure_locked(voted))\n",
        "",
    ),
    "a member keeps quiet when asked for another closure": (
        "            if voted is None:\n"
        "                return _NOTHING\n"
        "\n"
        "            return DriverOutput(replies=(encode_closure_locked(voted),))\n",
        "            return _NOTHING\n",
    ),
    "a closure not on disk": (
        "                    \"INSERT INTO closure_votes (epoch, digest, closure) VALUES (?, ?, ?)\",\n"
        "                    (epoch, digest, text),\n",
        "                    \"INSERT INTO closure_votes (epoch, digest) VALUES (?, ?)\",\n"
        "                    (epoch, digest),\n",
    ),
    "no takeover": (
        "            self._change = voted.change\n"
        "            return self._adopt(voted)\n",
        "            return _NOTHING\n",
    ),
    "retry at once": (
        "            or self._clock() - self._epoch_activity < self.EPOCH_RETRY_SECONDS\n",
        "",
    ),
    "retry again at once": (
        "        self._epoch_activity = self._clock()\n"
        "\n"
        "        if self._candidate is not None:\n"
        "            return DriverOutput(broadcasts=(encode_closure_vote_request(self._candidate),))\n",
        "        if self._candidate is not None:\n"
        "            return DriverOutput(broadcasts=(encode_closure_vote_request(self._candidate),))\n",
    ),
    "the order is not sent again": (
        "        return DriverOutput(broadcasts=(encode_epoch_change(self._change),))\n",
        "        return _NOTHING\n",
    ),
    "any closure adopted": (
        "            or not closure.is_valid_candidate(self.governance, self.committee)\n"
        "        ):\n"
        "            return _NOTHING\n"
        "\n"
        "        return self._adopt(closure)\n",
        "        ):\n"
        "            return _NOTHING\n"
        "\n"
        "        return self._adopt(closure)\n",
    ),
    "adopted without working on the order": (
        "            or self._change is None\n"
        "            or closure.change.change_id != self._change.change_id\n",
        "",
    ),
    "adopted again and again": (
        "            or (self._candidate is not None and self._candidate.digest == closure.digest)\n",
        "",
    ),
    "voted closure of an invalid form taken over": (
        "            if voted is None or not voted.is_valid_candidate(self.governance, self.committee):\n"
        "                return _NOTHING\n",
        "            if voted is None:\n"
        "                return _NOTHING\n",
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
