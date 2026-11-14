"""The tests of tests/test_certificate_lookup.py must be able to fail."""

from pathlib import Path

import pytest

from tests.mutation_support import ROOT, run_tests_on, source_of_module

TESTS = [str(Path("tests") / "test_certificate_lookup.py")]

MUTATIONS = {
    "network.quorum": {
        "not indexed when executed": (
            "        self.log.append(certificate)\n        self._log_by_id[certificate.event.event_id()] = certificate\n",
            "        self.log.append(certificate)\n",
        ),
        "not indexed at a restart": (
            "                self.log.append(certificate)\n                self._log_by_id[certificate.event.event_id()] = certificate\n",
            "                self.log.append(certificate)\n",
        ),
        "pruned but still found": (
            "            for certificate in covered:\n                self._log_by_id.pop(certificate.event.event_id(), None)\n",
            "",
        ),
        "the log scanned again": (
            "        return self._log_by_id.get(event_id)\n",
            "        return next((c for c in self.log if c.event.event_id() == event_id), None)\n",
        ),
    },
    "network.service": {
        "the API scans the log": (
            "            found = self.node._quorum.replica.certificate_of(event_id)\n",
            "            found = next((c for c in self.node._quorum.replica.log if c.event.event_id() == event_id), None)\n",
        ),
    },
}

CASES = [(module, name) for module, table in MUTATIONS.items() for name in table]


def source_of(module: str) -> str:
    return source_of_module(module)


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
