"""The tests of tests/test_stuck_event.py must be able to fail.

Left out: test_a_burst_is_not_lost_to_a_call_back and test_a_burst_lost_with_two_connections_runs_all_the_same,
whose nodes are separate processes that import the real modules. Each was seen to fail by hand without
the correction, with scripts/probe_stuck_event.py.
"""

from pathlib import Path

import pytest

from tests.mutation_support import ROOT, run_tests_on, source_of_module

TESTS = [str(Path("tests") / "test_stuck_event.py"), "-k", "not burst"]

MUTATIONS = {
    "network.node": {
        "the node with the lower id calls back": (
            "                if connection is not None and connection.connected:\n                    continue\n",
            "                if connection is not None and connection.connected and (\n"
            "                    connection.initiated_locally or self.node_id > peer.node_id\n"
            "                ):\n                    continue\n",
        ),
        "a new connection does not end the wait": (
            "                self._quorum.driver.resend_soon()\n",
            "                pass\n",
        ),
    },
    "network.quorum": {
        "asked again at once": (
            "                self._clock() + self.RESEND_FIRST_SECONDS,\n",
            "                self._clock(),\n",
        ),
        "never asked again": (
            "*snapshot.broadcasts, *self._resend_requests(), *rounds)",
            "*snapshot.broadcasts, *rounds)",
        ),
        "always the same wait": (
            "            pending.wait = min(2 * pending.wait, self.RESEND_LONGEST_SECONDS)\n",
            "",
        ),
        "the wait has no end": (
            "            pending.wait = min(2 * pending.wait, self.RESEND_LONGEST_SECONDS)\n",
            "            pending.wait = 2 * pending.wait\n",
        ),
        "no limit in a round": (
            "            self.RESEND_MOST_IN_A_ROUND,\n            (pending",
            "            10**9,\n            (pending",
        ),
        "the lowest nonce always first": (
            "            key=lambda pending: (pending.due, pending.signed.transfer.nonce),\n",
            "            key=lambda pending: pending.signed.transfer.nonce,\n",
        ),
        "asked again with a certificate held": (
            "                or known is not None\n",
            "",
        ),
        "asked again with the votes gone": (
            "                canonical not in self._aggregating\n                or known is not None\n",
            "                known is not None\n",
        ),
        "the votes stay after a certificate": (
            "                del self._to_resend[canonical]\n                self._aggregating.pop(canonical, None)\n\n",
            "                del self._to_resend[canonical]\n\n",
        ),
        "a new connection leaves the wait as it was": (
            "            pending.wait = self.RESEND_FIRST_SECONDS\n",
            "",
        ),
    },
}

ALL = [(module, name) for module, table in MUTATIONS.items() for name in table]


def source_of(module: str) -> str:
    return source_of_module(module)


@pytest.mark.parametrize("module,name", ALL)
def test_mutation_is_detected(module, name):
    old, new = MUTATIONS[module][name]
    source = source_of(module)
    assert source.count(old) == 1, name
    result = run_tests_on(module, source.replace(old, new), TESTS)
    assert result.returncode == 1, result.stdout + result.stderr
