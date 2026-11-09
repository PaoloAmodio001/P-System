"""The tests of tests/test_vote_never_executable.py must be able to fail."""

from pathlib import Path

import pytest

from tests.mutation_support import ROOT, run_tests_on

TESTS = [str(Path("tests") / "test_vote_never_executable.py")]

MUTATIONS = {
    "core.attestation": {
        "a zero amount can run": (
            "    return event.amount > 0 and event.sender != event.receiver\n",
            "    return event.sender != event.receiver\n",
        ),
        "a transfer to self can run": (
            "    return event.amount > 0 and event.sender != event.receiver\n",
            "    return event.amount > 0\n",
        ),
    },
    "network.quorum": {
        "the runtime votes for anything": (
            "                can_ever_execute,\n",
            "                lambda _event: True,\n",
        ),
    },
}

PATHS = {
    "core.attestation": ROOT / "core" / "attestation.py",
    "network.quorum": ROOT / "network" / "quorum.py",
}

CASES = [(module, name) for module, mutations in MUTATIONS.items() for name in mutations]


@pytest.mark.parametrize("module", MUTATIONS)
def test_the_tests_pass_on_the_real_source(module):
    result = run_tests_on(module, PATHS[module].read_text(), TESTS)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(("module", "name"), CASES)
def test_mutation_is_detected(module, name):
    old, new = MUTATIONS[module][name]
    source = PATHS[module].read_text()
    assert source.count(old) == 1, name
    result = run_tests_on(module, source.replace(old, new), TESTS)
    assert result.returncode == 1, result.stdout + result.stderr
