"""The tests of tests/test_snapshot_request_cost.py must be able to fail."""

from pathlib import Path

import pytest

from tests.mutation_support import ROOT, quorum_source, run_tests_on

TESTS = [str(Path("tests") / "test_snapshot_request_cost.py")]
SOURCE = quorum_source()

MUTATIONS = {
    "the work is free": (
        "            self._cost += work // SNAPSHOT_STEPS_PER_TOKEN\n",
        "",
    ),
    "a false digest is free": (
        "                if work:\n                    self._cost += BAD_SIGNATURE_COST\n",
        "",
    ),
    "never answered from memory": (
        "            self._snapshot_answers[key] = attestation\n",
        "",
    ),
    "the base is not in the key": (
        "        key = (self.committee.committee_id, base, epoch, digest, tuple(sorted(nonces.items())))\n",
        "        key = (self.committee.committee_id, epoch, digest, tuple(sorted(nonces.items())))\n",
    ),
    "the scan is not counted": (
        "        self.derive_steps += len(self.log)\n",
        "",
    ),
}


def test_the_tests_pass_on_the_real_source():
    result = run_tests_on("network.quorum", SOURCE, TESTS)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("name", MUTATIONS)
def test_mutation_is_detected(name):
    old, new = MUTATIONS[name]
    assert SOURCE.count(old) == 1, name
    result = run_tests_on("network.quorum", SOURCE.replace(old, new), TESTS)
    assert result.returncode == 1, result.stdout + result.stderr
