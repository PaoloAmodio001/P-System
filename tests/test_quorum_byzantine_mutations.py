"""The tests of tests/test_quorum_byzantine.py must be able to fail.

Each mutation breaks one rule that the absence of a fork rests on. Same method as
test_quorum_halt_mutations.py, on three modules. The tests on real TLS and with a worker
process stay out: the worker imports the real module, and TLS adds only time here.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from tests.mutation_support import quorum_source, source_argument

ROOT = Path(__file__).resolve().parent.parent
ATTESTATION = (ROOT / "core" / "attestation.py").read_text()
QUORUM = quorum_source()

# In this order, because each module takes names from the one before when it is imported.
RUNNER = """
import sys

from tests.mutation_support import apply_source

import core.attestation

try:
    exec(compile(sys.argv[1], "core/attestation.py", "exec"), core.attestation.__dict__)
    import network.quorum
    apply_source("network.quorum", sys.argv[2])
except Exception:
    # Python exits with 1 on an uncaught exception, the same as a failing test.
    sys.exit(3)

import pytest

sys.exit(pytest.main(sys.argv[3:]))
"""

TESTS = [
    "tests/test_quorum_byzantine.py",
    "-k",
    "not real_tls and not death_of_the_process",
    "-q",
    "-x",
    "--no-header",
    "-p",
    "no:cacheprovider",
]

IN_ATTESTATION = {
    "quorum of f + 1": (
        "        return (4 if self.unlock else 2) * self.f + 1\n",
        "        return self.f + 1\n",
    ),
    "signatures of a certificate not checked": (
        "        return all(\n"
        "            vote._verify_payload(committee, payload)\n"
        "            for vote in self.votes\n"
        "        )\n",
        "        return True\n",
    ),
    "repeated signers counted": (
        "        if len(set(signers)) != len(signers):\n"
        "            return False\n",
        "",
    ),
}

IN_QUORUM = {
    # The lock is kept twice: by the store, and by the step `request` of the Lean core in the
    # replica. Either alone holds it, so the mutation removes both.
    "vote lock removed": [
        (
            '                if rows and not lean_core.vote_allowed(\n',
            '                if False and not lean_core.vote_allowed(\n',
        ),
        (
            '            if round_state["vote0"] != event.event_id():\n'
            "                return None\n",
            "",
        ),
    ],
    "a vote executes": (
        '            return Vote.create(self.committee, self._identity, event)\n',
        '            rows = self._runs_on(self.state, self._executed_ids, event)\n            if rows is not None:\n                self._execute(QuorumCertificate(event, ()), rows)\n            return Vote.create(self.committee, self._identity, event)\n',
    ),
    "a node refuses a certificate against its own vote": (
        '        checks = self._checks(certificate, quorum, committee)\n        if checks is None:\n            return None\n',
        '        checks = self._checks(certificate, quorum, committee)\n        if checks is None or any(\n            (v.sender, v.nonce) == (event.sender, event.nonce) and v.canonical() != event.canonical()\n            for v in self._store.votes()\n        ):\n            return None\n',
    ),
    "conflict not noticed": (
        '            self.replica.record_halt(known, certificate)\n            self._halted_now()\n            return False\n',
        '            return False\n',
    ),
    "second alternative runs": (
        '            self.replica.record_halt(known, certificate)\n            self._halted_now()\n            return False\n',
        '            self.replica.record_halt(known, certificate)\n            self._halted_now()\n            self.replica.state.balances[event.receiver] = (\n                self.replica.state.balance(event.receiver) + event.amount\n            )\n            return False\n',
    ),
    "buffer not retried": (
        "            self._no_longer_waiting(event_id)\n"
        "            following = self._waiting.get(certificate.event.sender, {}).get(\n",
        "            self._no_longer_waiting(event_id)\n"
        "            return\n"
        "            following = self._waiting.get(certificate.event.sender, {}).get(\n",
    ),
}


def _run(attestation: str, quorum: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", RUNNER, attestation, source_argument(quorum), *TESTS],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=180,
    )


def test_the_tests_pass_on_the_real_source():
    result = _run(ATTESTATION, QUORUM)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("name", IN_ATTESTATION)
def test_mutation_in_attestation_is_detected(name):
    old, new = IN_ATTESTATION[name]
    assert ATTESTATION.count(old) == 1, name
    result = _run(ATTESTATION.replace(old, new), QUORUM)
    assert result.returncode == 1, result.stdout + result.stderr


@pytest.mark.parametrize("name", IN_QUORUM)
def test_mutation_in_quorum_is_detected(name):
    pairs = IN_QUORUM[name]
    mutated = QUORUM
    for old, new in [pairs] if isinstance(pairs, tuple) else pairs:
        assert mutated.count(old) == 1, name
        mutated = mutated.replace(old, new)
    result = _run(ATTESTATION, mutated)
    assert result.returncode == 1, result.stdout + result.stderr
