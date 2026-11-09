"""The tests of tests/test_wallet_index.py must be able to fail."""

from pathlib import Path

import pytest

from tests.mutation_support import ROOT, run_tests_on

TESTS = [str(Path("tests") / "test_wallet_index.py")]
SOURCE = (ROOT / "sdk" / "client.py").read_text()

MUTATIONS = {
    "no index": (
        '                "CREATE INDEX IF NOT EXISTS events_by_nonce ON events (CAST(nonce AS INTEGER))"\n',
        '                "SELECT 1"\n',
    ),
    "the largest nonce as text": (
        '        row = self._connection.execute("SELECT MAX(CAST(nonce AS INTEGER)) FROM events").fetchone()\n'
        "        return 0 if row[0] is None else row[0] + 1\n",
        '        row = self._connection.execute("SELECT MAX(nonce) FROM events").fetchone()\n'
        "        return 0 if row[0] is None else int(row[0]) + 1\n",
    ),
    "unfinished in the order of text": (
        "            ORDER BY CAST(nonce AS INTEGER)\n            \"\"\",\n",
        "            ORDER BY nonce\n            \"\"\",\n",
    ),
    "unfinished from the start": (
        "            WHERE CAST(nonce AS INTEGER) >= ?\n",
        "            WHERE ? IS NOT NULL\n",
    ),
    "any nonce signed": (
        "        if type(nonce) is not int or not 0 <= nonce <= MAX_WALLET_NONCE:\n",
        "        if False:\n",
    ),
}


def test_the_tests_pass_on_the_real_source():
    result = run_tests_on("sdk.client", SOURCE, TESTS)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("name", MUTATIONS)
def test_mutation_is_detected(name):
    old, new = MUTATIONS[name]
    assert SOURCE.count(old) == 1, name
    result = run_tests_on("sdk.client", SOURCE.replace(old, new), TESTS)
    assert result.returncode == 1, result.stdout + result.stderr
