"""The tests of tests/test_quorum_old_keys.py must be able to fail."""

from pathlib import Path

import pytest

from tests.mutation_support import ROOT, run_tests_on

TESTS = [str(Path("tests") / "test_quorum_old_keys.py")]

CHANGES = {
    ("network.quorum", "network/quorum.py"): {
        "old certificates believed": (
            "        return certificate.verify(self._store.committee_of(certificate)) and (\n"
            "            certificate.epoch >= self.committee.epoch\n"
            "            or self._store.is_locked_event(certificate.event)\n"
            "        )\n",
            "        return certificate.verify(self._store.committee_of(certificate))\n",
        ),
        "signatures of old certificates not checked": (
            "        return certificate.verify(self._store.committee_of(certificate)) and (\n"
            "            certificate.epoch >= self.committee.epoch\n"
            "            or self._store.is_locked_event(certificate.event)\n"
            "        )\n",
            "        return certificate.epoch < self.committee.epoch or certificate.verify(self._store.committee_of(certificate))\n",
        ),
        "every certificate needs a lock": (
            "            certificate.epoch >= self.committee.epoch\n"
            "            or self._store.is_locked_event(certificate.event)\n",
            "            self._store.is_locked_event(certificate.event)\n",
        ),
        "the replay applies the rule of arrival": (
            "        return self._can_run_now(certificate.event) and self.certificate_was_valid(certificate)\n",
            "        return self._can_run_now(certificate.event) and self.certificate_is_valid(certificate)\n",
        ),
        "a lock on the spend, not the event": (
            "                        \"SELECT 1 FROM locks WHERE sender = ? AND nonce = ? AND canonical = ?\",\n"
            "                        (event.sender, str(event.nonce), event.canonical().decode()),\n",
            "                        \"SELECT 1 FROM locks WHERE sender = ? AND nonce = ?\",\n"
            "                        (event.sender, str(event.nonce)),\n",
        ),
        "old conflict halts": (
            "            if certificate.epoch < self.committee.epoch:\n"
            "                LOG.warning(\n"
            "                    \"conflicting certificate of an ended committee ignored\",\n"
            "                    extra={\"sender\": event.sender, \"nonce\": event.nonce, \"epoch\": certificate.epoch},\n"
            "                )\n"
            "                return\n",
            "",
        ),
        "no conflict halts": (
            "            if certificate.epoch < self.committee.epoch:\n"
            "                LOG.warning(\n",
            "            if True:\n"
            "                LOG.warning(\n",
        ),
    },
    ("sdk.client", "sdk/client.py"): {
        "light client believes old certificates": (
            "            and (\n"
            "                certificate.epoch >= self.current.epoch\n"
            "                or certificate.event.canonical() in self._locks\n"
            "            )\n",
            "",
        ),
        "light client takes no locks": (
            "            self._locks.update(event.canonical() for event in closure.locks())\n",
            "",
        ),
        "light client wants a lock for everything": (
            "                certificate.epoch >= self.current.epoch\n"
            "                or certificate.event.canonical() in self._locks\n",
            "                certificate.event.canonical() in self._locks\n",
        ),
    },
}

CASES = [
    (module, file, name, change)
    for (module, file), mutations in CHANGES.items()
    for name, change in mutations.items()
]


@pytest.mark.parametrize("case", CASES, ids=[case[2] for case in CASES])
def test_mutation_is_detected(case):
    module, file, _, (old, new) = case
    source = (ROOT / file).read_text()
    assert source.count(old) == 1
    result = run_tests_on(module, source.replace(old, new), TESTS)
    assert result.returncode == 1, result.stdout + result.stderr
