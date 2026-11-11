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
        "a prepare of round 0 below the quorum": (
            "        if len(votes) < self.committee.quorum:\n            return []\n\n"
            "        certificate = QuorumCertificate(\n            event,\n"
            "            tuple(votes[validator] for validator in sorted(votes)),\n"
            "            self.committee.epoch,\n        )\n",
            "        if len(votes) < self.committee.quorum - 1:\n            return []\n\n"
            "        certificate = QuorumCertificate(\n            event,\n"
            "            tuple(votes[validator] for validator in sorted(votes)),\n"
            "            self.committee.epoch,\n        )\n",
        ),
        "a certificate of a round below the quorum": (
            "        if len(votes) < self.committee.quorum:\n            return []\n\n"
            "        certificate = QuorumCertificate(\n            event,\n"
            "            tuple(votes[validator] for validator in sorted(votes)),\n"
            "            self.committee.epoch,\n            phase,\n",
            "        if len(votes) < self.committee.quorum - 1:\n            return []\n\n"
            "        certificate = QuorumCertificate(\n            event,\n"
            "            tuple(votes[validator] for validator in sorted(votes)),\n"
            "            self.committee.epoch,\n            phase,\n",
        ),
        "a proposal on fewer reports than a quorum": (
            "        reports = self.reports.get((sender, nonce, round_), {})\n"
            "        if len(reports) < self.committee.quorum:\n",
            "        reports = self.reports.get((sender, nonce, round_), {})\n"
            "        if len(reports) < self.committee.quorum - 1:\n",
        ),
        "a prepare by sync taken as a decision": (
            "            if not certificate.decides(self.replica.committee_of(certificate)):\n"
            "                self._cost += BAD_SIGNATURE_COST\n"
            "                return _NOTHING\n",
            "",
        ),
        "a prepare not sent on": (
            "            out = [encode_certificate(certificate, signed), *out]\n",
            "            pass\n",
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
