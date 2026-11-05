"""Differential D must be able to fail: each mutation breaks one rule across epochs."""

from pathlib import Path

import pytest

from tests.mutation_support import ROOT, run_tests_on

TESTS = [str(Path("tests") / "test_epoch_differential.py"), "-k", "20261105"]

QUORUM = {
    "locks ignored": (
        "                if self._is_locked_against(event, canonical):\n"
        "                    return False\n",
        "",
    ),
    "a lock blocks its own event too": (
        "            row[0] != canonical\n",
        "            True\n",
    ),
    "a lock on the sender only": (
        "                \"SELECT canonical FROM locks WHERE sender = ? AND nonce = ?\",\n"
        "                (event.sender, str(event.nonce)),\n",
        "                \"SELECT canonical FROM locks WHERE sender = ?\",\n"
        "                (event.sender,),\n",
    ),
    "a closed epoch still votes": (
        "                if self._is_closed(epoch):\n"
        "                    return False\n",
        "",
    ),
    "closing is not durable": (
        "                self._connection.execute(\n"
        "                    \"INSERT OR IGNORE INTO closed_epochs (epoch) VALUES (?)\",\n"
        "                    (epoch,),\n"
        "                )\n",
        "",
    ),
    "locks of a closure not recorded": (
        "                self._connection.executemany(\n"
        "                    \"\"\"\n"
        "                    INSERT OR IGNORE INTO locks (sender, nonce, canonical)\n"
        "                    VALUES (?, ?, ?)\n"
        "                    \"\"\",\n"
        "                    [\n"
        "                        (event.sender, str(event.nonce), event.canonical().decode())\n"
        "                        for event in locks\n"
        "                    ],\n"
        "                )\n",
        "",
    ),
    "votes of the last epoch stay": (
        "                    \"SELECT canonical FROM votes WHERE epoch = ? ORDER BY rowid\",\n"
        "                    (self.committee.epoch,),\n",
        "                    \"SELECT canonical FROM votes WHERE epoch <= ? ORDER BY rowid\",\n"
        "                    (self.committee.epoch,),\n",
    ),
    "vote lock across epochs": (
        "                        WHERE epoch = ? AND ((sender = ? AND nonce = ?) OR event_id = ?)\n"
        "                        \"\"\",\n"
        "                        (epoch, event.sender, str(event.nonce), event_id),\n",
        "                        WHERE epoch <= ? AND ((sender = ? AND nonce = ?) OR event_id = ?)\n"
        "                        \"\"\",\n"
        "                        (epoch, event.sender, str(event.nonce), event_id),\n",
    ),
    "the report misses votes": (
        "                    WHERE votes.epoch = ?\n"
        "                    \"\"\",\n",
        "                    WHERE votes.epoch = ? LIMIT 1\n"
        "                    \"\"\",\n",
    ),
}

ATTESTATION = {
    "locks only of the first report": (
        "        for report in self.reports:\n"
        "            for canonical in {signed.transfer.canonical() for signed in report.votes}:\n",
        "        for report in self.reports[:1]:\n"
        "            for canonical in {signed.transfer.canonical() for signed in report.votes}:\n",
    ),
}

CASES = [
    *(("network.quorum", "network/quorum.py", name, change) for name, change in QUORUM.items()),
    *(("core.attestation", "core/attestation.py", name, change) for name, change in ATTESTATION.items()),
]


@pytest.mark.parametrize("case", CASES, ids=[case[2] for case in CASES])
def test_mutation_is_detected(case):
    module, file, _, (old, new) = case
    source = (ROOT / file).read_text()
    assert source.count(old) == 1
    result = run_tests_on(module, source.replace(old, new), TESTS)
    assert result.returncode == 1, result.stdout + result.stderr
