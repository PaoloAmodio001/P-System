"""The tests of tests/test_resend_after_restart.py must be able to fail.

Left out: test_a_node_killed_while_gathering_finishes_when_it_comes_back and
test_the_metrics_of_a_real_node_say_what_is_stuck, whose nodes are separate processes that import the real
modules. The first was seen to fail by hand without the change: see docs/piano-bizantino.md.
"""

from pathlib import Path

import pytest

from tests.mutation_support import ROOT, run_tests_on

TESTS = [
    str(Path("tests") / "test_resend_after_restart.py"),
    str(Path("tests") / "test_quorum_reports.py"),
    "-k",
    "not killed and not real_node",
]

MUTATIONS = {
    "network.quorum": {
        "the taken event is not written": (
            "self.replica.handle_vote_request(event, signed, gathering=True)",
            "self.replica.handle_vote_request(event, signed)",
        ),
        "written only for a first vote": (
            "                    if gathering:\n                        self._record_gathering(epoch, event_id)\n"
            "                        self._commit()\n\n                    return True\n",
            "                    return True\n",
        ),
        "a certificate leaves the row": (
            '                self._connection.execute(\n                    "DELETE FROM gathering WHERE event_id = ?",\n'
            "                    (event.event_id(),),\n                )\n",
            "",
        ),
        "a closure leaves the row": (
            '                self._connection.execute(\n                    "DELETE FROM gathering WHERE epoch <= ?",\n'
            "                    (current.epoch,),\n                )\n",
            "",
        ),
        "nothing resumes after a restart": (
            "        if not self.halted:\n            self._resume_gathering()\n",
            "",
        ),
        "resumes after a halt": (
            "        if not self.halted:\n            self._resume_gathering()\n",
            "        self._resume_gathering()\n",
        ),
        "no limit on what resumes": (
            "self.replica.gathering()[: self.max_aggregating]",
            "self.replica.gathering()",
        ),
        "waits a whole turn after a restart": (
            "                signed,\n                self._clock(),\n                self.RESEND_FIRST_SECONDS,\n"
            "                self._clock(),\n                needs_own_vote=True,\n",
            "                signed,\n                self._clock() + self.RESEND_FIRST_SECONDS,\n"
            "                self.RESEND_FIRST_SECONDS,\n                self._clock(),\n"
            "                needs_own_vote=True,\n",
        ),
        "its own vote does not come back": (
            "                needs_own_vote=True,\n",
            "",
        ),
        "a certificate in memory loses the row": (
            "                if known is None or known.event.canonical() != canonical:\n",
            "                if True:\n",
        ),
        "another version certified keeps the row": (
            "                if known is None or known.event.canonical() != canonical:\n",
            "                if known is None:\n",
        ),
        "the count of requests stands still": (
            "        self.requests_resent += len(messages)\n",
            "",
        ),
        "the oldest is the newest": (
            "next(iter(self._to_resend.values()), None)",
            "next(reversed(self._to_resend.values()), None)",
        ),
        "a certificate stays in the numbers": (
            "        self._to_resend.pop(event.canonical(), None)\n",
            "",
        ),
        "a file of schema 5 refused": (
            "(_SCHEMA_VERSION, _SCHEMA_VERSION_5, _SCHEMA_VERSION_4)",
            "(_SCHEMA_VERSION, _SCHEMA_VERSION_4)",
        ),
        "a migration without the table": (
            "                self._connection.execute(_GATHERING_TABLE)\n",
            "",
        ),
        "a file of schema 5 gets the older migration": (
            "            if version not in (_SCHEMA_VERSION, _SCHEMA_VERSION_5):\n",
            "            if version != _SCHEMA_VERSION:\n",
        ),
    },
    "network.node": {
        "a replacement is not counted": (
            "                    self.connections_replaced += 1\n",
            "",
        ),
    },
}

ALL = [(module, name) for module, table in MUTATIONS.items() for name in table]


def source_of(module: str) -> str:
    return (ROOT / (module.replace(".", "/") + ".py")).read_text()


@pytest.mark.parametrize("module,name", ALL)
def test_mutation_is_detected(module, name):
    old, new = MUTATIONS[module][name]
    source = source_of(module)
    assert source.count(old) == 1, name
    result = run_tests_on(module, source.replace(old, new), TESTS)
    assert result.returncode == 1, result.stdout + result.stderr
