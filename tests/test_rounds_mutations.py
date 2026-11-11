"""The tests of rounds must be able to fail: each mutation breaks one rule, and they notice."""

import pytest

from tests.mutation_support import quorum_source, run_tests_on, source_of_module

TESTS = ["tests/test_rounds_split.py", "tests/test_quorum_driver.py"]

MUTATIONS = {
    "core.attestation": {
        "a prepare certificate decides": (
            "        return self.phase == VOTE and len(self.votes) >= committee.n\n",
            "        return self.phase == VOTE and len(self.votes) >= committee.quorum\n",
        ),
    },
    "network.quorum": {
        "the timeout never fires": (
            '            if now - since >= self.timeout_of(state["round"]):\n',
            "            if False:\n",
        ),
        "a proposal is taken from anyone": (
            "        if not proposal.verify_leader(self.committee, self.leader(sender, nonce, proposal.round)):\n",
            "        if not proposal.verify_leader(self.committee, proposal.validator):\n",
        ),
    },
}

CASES = [(module, name) for module, mutations in MUTATIONS.items() for name in mutations]


def source(module: str) -> str:
    return quorum_source() if module == "network.quorum" else source_of_module(module)


@pytest.mark.parametrize("module", MUTATIONS)
def test_the_tests_pass_on_the_real_source(module):
    result = run_tests_on(module, source(module), TESTS)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("module,name", CASES)
def test_mutation_is_detected(module, name):
    old, new = MUTATIONS[module][name]
    text = source(module)
    assert text.count(old) == 1, name
    result = run_tests_on(module, text.replace(old, new), TESTS)
    assert result.returncode == 1, result.stdout + result.stderr
