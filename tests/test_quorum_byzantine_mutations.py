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
    "vote lock removed": (
        "                if existing - {canonical}:\n"
        "                    return False\n",
        "",
    ),
    "a vote executes": (
        "            return Vote.create(self.committee, self._identity, event)\n",
        "            if self._is_fresh(event) and self._is_ready(event) and"
        " self._is_executable(event):\n"
        "                self._execute(QuorumCertificate(event, ()))\n"
        "            return Vote.create(self.committee, self._identity, event)\n",
    ),
    "a node refuses a certificate against its own vote": (
        "        return self._can_run_now(certificate.event) and self.certificate_is_valid(certificate)\n",
        "        event = certificate.event\n"
        "        return (\n"
        "            self._can_run_now(event)\n"
        "            and self.certificate_is_valid(certificate)\n"
        "            and not any(\n"
        "                (v.sender, v.nonce) == (event.sender, event.nonce)\n"
        "                and v.canonical() != event.canonical()\n"
        "                for v in self._store.votes()\n"
        "            )\n"
        "        )\n",
    ),
    "conflict not noticed": (
        "            self.replica.record_halt(known, certificate)\n"
        "            self._buffer.clear()\n"
        "            self._waiting.clear()\n"
        "            self._aggregating.clear()\n"
        "            return False\n",
        "            return False\n",
    ),
    "second alternative runs": (
        "            self.replica.record_halt(known, certificate)\n"
        "            self._buffer.clear()\n"
        "            self._waiting.clear()\n"
        "            self._aggregating.clear()\n"
        "            return False\n",
        # The halt stays, or this would die on the same line as the mutation above.
        "            self.replica.record_halt(known, certificate)\n"
        "            self._buffer.clear()\n"
        "            self._waiting.clear()\n"
        "            self._aggregating.clear()\n"
        "            self.replica.state.balances[event.receiver] = (\n"
        "                self.replica.state.balance(event.receiver) + event.amount\n"
        "            )\n"
        "            return False\n",
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
    old, new = IN_QUORUM[name]
    assert QUORUM.count(old) == 1, name
    result = _run(ATTESTATION, QUORUM.replace(old, new))
    assert result.returncode == 1, result.stdout + result.stderr
