"""The tests of tests/test_supply_conservation.py must be able to fail."""

from pathlib import Path

import pytest

from tests.mutation_support import ROOT, run_tests_on

TESTS = [str(Path("tests") / "test_supply_conservation.py")]

MUTATIONS = {
    "core.attestation": {
        "any two assets are one": (
            "    return account_asset(event.sender) == account_asset(event.receiver)\n",
            "    return True\n",
        ),
    },
    "network.quorum": {
        "the node votes across assets": (
            "                stays_in_one_asset,\n",
            "                lambda _event: True,\n",
        ),
        "the replica refuses nothing by auth": (
            "        if not self._auth(event):\n            return None\n",
            "",
        ),
    },
    "network.service": {
        "the API passes it on": (
            "            for event in events:\n                check_supply_conservation(event.transfer)\n",
            "            pass\n",
        ),
    },
    "core.derive": {
        "execution looks at assets": (
            '        """Return why `event` cannot execute on `state`, or None."""\n',
            '        """Return why `event` cannot execute on `state`, or None."""\n'
            "        check_supply_conservation(event)\n",
        ),
    },
}

CASES = [(module, name) for module, mutations in MUTATIONS.items() for name in mutations]


def source_of(module: str) -> str:
    return (ROOT / (module.replace(".", "/") + ".py")).read_text()


@pytest.mark.parametrize("module", MUTATIONS)
def test_the_tests_pass_on_the_real_source(module):
    result = run_tests_on(module, source_of(module), TESTS)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(("module", "name"), CASES)
def test_mutation_is_detected(module, name):
    old, new = MUTATIONS[module][name]
    source = source_of(module)
    assert source.count(old) == 1, name
    result = run_tests_on(module, source.replace(old, new), TESTS)
    assert result.returncode == 1, result.stdout + result.stderr
