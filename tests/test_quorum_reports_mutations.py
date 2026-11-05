"""The tests of tests/test_quorum_reports.py must be able to fail.

The test with real nodes stays out: each process would import the module as it is, and it takes seconds.

Not here on purpose: `INSERT OR IGNORE` of the lock in place of `INSERT OR REPLACE`. The check before it
returns for any other order, so what reaches the write is the same order or none.
"""

from pathlib import Path

import pytest

from tests.mutation_support import ROOT, run_tests_on

TESTS = [str(Path("tests") / "test_quorum_reports.py"), "-k", "not real_proposers"]

QUORUM = {
    "a report for any order": (
        "                if lock is not None and lock[0] != change.change_id:\n                    return None\n",
        "",
    ),
    "the lock on the order not written": (
        '                self._connection.execute(\n                    "INSERT OR IGNORE INTO report_locks (epoch, change_id, change) VALUES (?, ?, ?)",\n                    (epoch, change.change_id, _change_text(change)),\n                )\n',
        "",
    ),
    "an epoch closed with no order reports anyway": (
        "                if lock is None and self._is_closed(epoch):\n                    return None\n",
        "",
    ),
    "report given though the lock refused": (
        "        if votes is None:\n            return None\n\n        try:\n            return EpochReport.create(self.committee, self._identity, change.change_id, votes)\n",
        "        votes = votes or []\n\n        try:\n            return EpochReport.create(self.committee, self._identity, change.change_id, votes)\n",
    ),
    "a report for an order that does not verify": (
        "        if (\n            self.governance is None\n            or self.halted\n            or not change.verify(self.governance, self.committee)\n        ):\n            return _NOTHING\n\n        report = self.replica.report_epoch(change)\n\n        if report is None:\n",
        "        if self.governance is None or self.halted:\n            return _NOTHING\n\n        report = self.replica.report_epoch(change)\n\n        if report is None:\n",
    ),
    "a proposer does not report": (
        "        report = self.replica.report_epoch(change)\n\n        if report is not None:\n            self._reports[report.validator] = report\n\n        closed = self._closure_if_reported()\n        return DriverOutput(broadcasts=(encode_epoch_change(change), *closed.broadcasts))\n",
        "        closed = self._closure_if_reported()\n        return DriverOutput(broadcasts=(encode_epoch_change(change), *closed.broadcasts))\n",
    ),
    "a report of any order counted": (
        "            or change_id != self._change.change_id\n",
        "",
    ),
    "a report not verified": (
        "            or not report.verify(self.committee, change_id)\n",
        "",
    ),
    "reports with nothing proposed": (
        "            self._change is None\n            or change_id != self._change.change_id\n",
        "            change_id != getattr(self._change, 'change_id', change_id)\n",
    ),
    "a quorum of two": (
        "        if len(self._reports) < self.committee.quorum:\n",
        "        if len(self._reports) < self.committee.quorum - 1:\n",
    ),
    "a closure not sent": (
        "        self._install(closure)\n        return DriverOutput(broadcasts=(encode_epoch_closure(closure),))\n",
        "        self._install(closure)\n        return _NOTHING\n",
    ),
    "a closure not installed by who made it": (
        "        self._install(closure)\n        return DriverOutput(broadcasts=(encode_epoch_closure(closure),))\n",
        "        return DriverOutput(broadcasts=(encode_epoch_closure(closure),))\n",
    ),
    "no retry by a member": (
        "            if reported is None or not reported.verify(self.governance, self.committee):\n                return _NOTHING\n",
        "            return _NOTHING\n",
    ),
    "a retry with nothing to retry": (
        "            if reported is None or not reported.verify(self.governance, self.committee):\n                return _NOTHING\n\n            self._change = reported\n",
        "            self._change = reported or self._change\n",
    ),
    "a retry does not wait": (
        "            or self._clock() - self._epoch_activity < self.EPOCH_RETRY_SECONDS\n",
        "",
    ),
    "a retry does not start the wait again": (
        "        self._epoch_activity = self._clock()\n        closed = self._closure_if_reported()\n        return DriverOutput(broadcasts=(encode_epoch_change(self._change), *closed.broadcasts))\n",
        "        closed = self._closure_if_reported()\n        return DriverOutput(broadcasts=(encode_epoch_change(self._change), *closed.broadcasts))\n",
    ),
    "a halted node retries": (
        "            self.governance is None\n            or self.halted\n            or self._clock() - self._epoch_activity < self.EPOCH_RETRY_SECONDS\n",
        "            self.governance is None\n            or self._clock() - self._epoch_activity < self.EPOCH_RETRY_SECONDS\n",
    ),
    "a retry forgets its own report": (
        "            self._change = reported\n            report = self.replica.report_epoch(reported)\n\n            if report is not None:\n                self._reports[report.validator] = report\n",
        "            self._change = reported\n",
    ),
    "a voted closure gives no lock": (
        '            self._connection.execute(\n                "INSERT INTO report_locks (epoch, change_id, change) VALUES (?, ?, ?)",\n                (epoch, change.change_id, _change_text(change)),\n            )\n',
        "",
    ),
    "headers go out to peers": (
        "        if any(isinstance(closure, ClosureHeader) for closure in closures):\n            return []\n",
        "",
    ),
    "the last closure becomes a header too": (
        '                    (epoch - 1,),\n',
        '                    (epoch + 1,),\n',
    ),
    "closures stay whole": (
        '                            (_header_text(ClosureHeader.of(old)), old_epoch),\n',
        '                            (text, old_epoch),\n',
    ),
    "an unreadable closure is another error": (
        "            except (ValueError, KeyError, TypeError, RecursionError) as error:\n                raise VoteStoreError(\"CLOSURE IS UNREADABLE\") from error\n",
        "            except RecursionError as error:\n                raise VoteStoreError(\"CLOSURE IS UNREADABLE\") from error\n",
    ),
    "closures on file keep their votes": (
        '            body.pop("votes", None)\n',
        "",
    ),
}

ATTESTATION = {
    "any number of reports": (
        "            and len(validators) >= committee.quorum\n            and all(\n                report.verify",
        "            and all(\n                report.verify",
    ),
    "reports repeated or in any order": (
        "            and validators == sorted(set(validators))\n            and len(validators) >= committee.quorum\n            and all(\n                report.verify",
        "            and len(validators) >= committee.quorum\n            and all(\n                report.verify",
    ),
    "reports not checked": (
        "            and all(\n                report.verify(committee, self.change.change_id, checked)\n                for report in self.reports\n            )\n",
        "",
    ),
    "an order not checked": (
        "            self.change.verify(governance, committee)\n            and validators == sorted(set(validators))\n            and len(validators) >= committee.quorum\n            and all(\n                report.verify",
        "            validators == sorted(set(validators))\n            and len(validators) >= committee.quorum\n            and all(\n                report.verify",
    ),
    "a header with an order not checked": (
        "            self.change.verify(governance, committee)\n            and validators == sorted(set(validators))\n            and len(validators) >= committee.quorum\n            and all(\n                committee.has_validator",
        "            validators == sorted(set(validators))\n            and len(validators) >= committee.quorum\n            and all(\n                committee.has_validator",
    ),
    "a header with reports repeated": (
        "            and validators == sorted(set(validators))\n            and len(validators) >= committee.quorum\n            and all(\n                committee.has_validator",
        "            and len(validators) >= committee.quorum\n            and all(\n                committee.has_validator",
    ),
    "a header below a quorum": (
        "            and len(validators) >= committee.quorum\n            and all(\n                committee.has_validator",
        "            and all(\n                committee.has_validator",
    ),
    "a header with signatures not checked": (
        "                and verify_signature(\n                    committee.members[validator],\n                    signature,\n                    EpochReport._payload_of_digest(committee, self.change.change_id, digest),\n                )\n",
        "",
    ),
}

SIGNER = {
    "the guard gives any order": (
        '        return row == (change_id.hex(), digest)\n',
        '        return row[1] == digest or row[0] != change_id.hex()\n',
    ),
}

MESSAGE = {
    "a closure can carry anything": (
        '    data = _object_with_fields(value, "change", "reports")\n',
        '    data = dict(value)\n',
    ),
}

SOURCES = {
    "network.quorum": (ROOT / "network" / "quorum.py").read_text(),
    "core.attestation": (ROOT / "core" / "attestation.py").read_text(),
    "network.remote_signer": (ROOT / "network" / "remote_signer.py").read_text(),
    "network.message": (ROOT / "network" / "message.py").read_text(),
}

ALL = [
    ("network.quorum", QUORUM),
    ("core.attestation", ATTESTATION),
    ("network.remote_signer", SIGNER),
    ("network.message", MESSAGE),
]


@pytest.mark.parametrize("module", SOURCES)
def test_the_tests_pass_on_the_real_source(module):
    result = run_tests_on(module, SOURCES[module], TESTS)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    "module,name",
    [(module, name) for module, table in ALL for name in table],
)
def test_mutation_is_detected(module, name):
    old, new = dict(ALL)[module][name]
    source = SOURCES[module]
    assert source.count(old) == 1, name
    result = run_tests_on(module, source.replace(old, new), TESTS)
    assert result.returncode == 1, result.stdout + result.stderr
