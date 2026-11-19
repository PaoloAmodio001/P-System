"""The node-level differential across epochs (tests/test_epoch_differential_node.py) must be able to fail."""

import pytest

from tests.mutation_support import quorum_source, run_tests_on

TESTS = ["tests/test_epoch_differential_node.py", "-x", "-k", "20261105"]

MUTATIONS = {
    "the floor of a snapshot never applied": (
        "        if self.prune:\n            self.replica.apply_floor()\n",
        "",
    ),
    "a closed epoch still votes": (
        "                if self._is_closed(epoch):\n                    return False\n",
        "",
    ),
    "the locks of a closure ignored": (
        "                if self._is_locked_against(event, canonical):\n                    return False\n",
        "",
    ),
    "a vote under the floor": (
        "                if self._is_below_floor(event):\n                    return False\n",
        "",
    ),
}


def test_the_comparison_passes_on_the_real_source():
    result = run_tests_on("network.quorum", quorum_source(), TESTS)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("name", MUTATIONS)
def test_mutation_is_detected(name):
    old, new = MUTATIONS[name]
    source = quorum_source()
    assert source.count(old) == 1, name
    result = run_tests_on("network.quorum", source.replace(old, new), TESTS)
    assert result.returncode == 1, result.stdout + result.stderr
