"""The tests of tests/test_quorum_vote_store.py must be able to fail.

These replace the mutations of phase 5.2, whose script was lost with /tmp on 2026-11-04.
The counts of that time are not reused: only this file counts.

Each mutation breaks one rule of SqliteVoteStore in network/quorum.py.

The tests that start a process stay out, because that process imports the real module: the
crash tests and the test with two processes. No mutation here checks them.

Not here on purpose: the order in which `votes` reads the votes back. Nothing depends on it,
because the votes are a set in the model and every caller treats them as one.
"""

from pathlib import Path

import pytest

from tests.mutation_support import ROOT, run_tests_on

MODULE = "network.quorum"
SOURCE = (ROOT / "network" / "quorum.py").read_text()
TESTS = [
    str(Path("tests") / "test_quorum_vote_store.py"),
    "-k",
    "not crash and not two_processes and not kill_at_random",
]

MUTATIONS = {
    # Opening.
    "validator outside the committee": (
        "        if committee.index_of(validator) is None:\n"
        "            raise VoteStoreError(\"VALIDATOR IS NOT A COMMITTEE MEMBER\")\n",
        "",
    ),
    "missing file created without being asked": (
        "        mode = \"rwc\" if create else \"rw\"\n",
        "        mode = \"rwc\"\n",
    ),
    "empty file initialized without being asked": (
        "                if not create:\n"
        "                    raise VoteStoreError(\"VOTE STORE WAS NEVER INITIALIZED\")\n",
        "",
    ),
    "store of another validator or committee opened": (
        "            if found != expected:\n"
        "                raise VoteStoreError(\"VOTE STORE BELONGS TO ANOTHER VALIDATOR\")\n",
        "",
    ),
    "unknown schema version opened": (
        "            elif version != _SCHEMA_VERSION:\n"
        "                raise VoteStoreError(\"UNSUPPORTED VERSION OF THE VOTE STORE\")\n",
        "",
    ),
    "migration without the halt table": (
        "                self._connection.execute(_HALT_TABLE)\n",
        "",
    ),
    "migration does not record the version": (
        "                self._connection.execute(\n"
        "                    \"UPDATE meta SET value = ? WHERE key = 'schema_version'\",\n"
        "                    (_SCHEMA_VERSION,),\n"
        "                )\n",
        "",
    ),
    # Durability.
    "synchronous FULL": (
        "        self._connection.execute(\"PRAGMA synchronous = EXTRA\")\n",
        "        self._connection.execute(\"PRAGMA synchronous = FULL\")\n",
    ),
    "write-ahead log": (
        "        self._connection.execute(\"PRAGMA journal_mode = DELETE\").fetchall()\n",
        "        self._connection.execute(\"PRAGMA journal_mode = WAL\").fetchall()\n",
    ),
    "settings not checked after applying them": (
        "        if self._pragma(\"journal_mode\") != \"delete\" or self._pragma(\"synchronous\") != 3:\n"
        "            raise VoteStoreError(\"VOTE STORE IS NOT DURABLE\")\n",
        "",
    ),
    "write lock taken late": (
        "        self._connection.execute(\"BEGIN IMMEDIATE\")\n",
        "        self._connection.execute(\"BEGIN\")\n",
    ),
    # The vote lock.
    "vote lock removed": (
        "                if existing - {canonical}:\n"
        "                    return False\n",
        "",
    ),
    "same event again refused": (
        "                if existing:\n"
        "                    return True\n",
        "                if existing:\n"
        "                    return False\n",
    ),
    "lock on the sender only": (
        "                        WHERE (sender = ? AND nonce = ?) OR event_id = ?\n"
        "                        \"\"\",\n"
        "                        (event.sender, str(event.nonce), event_id),\n",
        "                        WHERE sender = ? OR event_id = ?\n"
        "                        \"\"\",\n"
        "                        (event.sender, event_id),\n",
    ),
    "lock ignores the id": (
        "                        WHERE (sender = ? AND nonce = ?) OR event_id = ?\n"
        "                        \"\"\",\n"
        "                        (event.sender, str(event.nonce), event_id),\n",
        "                        WHERE (sender = ? AND nonce = ?)\n"
        "                        \"\"\",\n"
        "                        (event.sender, str(event.nonce)),\n",
    ),
    "vote not committed": (
        "                    (event.sender, str(event.nonce), event_id, canonical),\n"
        "                )\n"
        "                self._commit()\n",
        "                    (event.sender, str(event.nonce), event_id, canonical),\n"
        "                )\n",
    ),
    "failed write reported as a refusal": (
        "                raise VoteStoreError(f\"VOTE NOT RECORDED: {error}\") from error\n",
        "                return False\n",
    ),
    "failed write reported as a vote": (
        "                raise VoteStoreError(f\"VOTE NOT RECORDED: {error}\") from error\n",
        "                return True\n",
    ),
    "transaction left open after a vote": (
        "                raise VoteStoreError(f\"VOTE NOT RECORDED: {error}\") from error\n"
        "            finally:\n"
        "                self._rollback_if_open()\n",
        "                raise VoteStoreError(f\"VOTE NOT RECORDED: {error}\") from error\n",
    ),
    "closed store still answers": (
        "        if self._closed:\n"
        "            raise VoteStoreError(\"VOTE STORE IS CLOSED\")\n",
        "        pass\n",
    ),
    # The log.
    "log read back in another order": (
        "                    \"SELECT canonical, signatures FROM certificates ORDER BY position\"\n",
        "                    \"SELECT canonical, signatures FROM certificates ORDER BY position DESC\"\n",
    ),
    "certificate not committed": (
        "                    (event.event_id(), event.canonical().decode(), signatures),\n"
        "                )\n"
        "                self._commit()\n",
        "                    (event.event_id(), event.canonical().decode(), signatures),\n"
        "                )\n",
    ),
    "failed write of a certificate ignored": (
        "                raise VoteStoreError(f\"CERTIFICATE NOT RECORDED: {error}\") from error\n",
        "                return\n",
    ),
    "signatures of the log lost": (
        "            Vote(validator, bytes.fromhex(signature))\n"
        "            for validator, signature in json.loads(signatures)\n",
        "            Vote(validator, bytes.fromhex(signature))\n"
        "            for validator, signature in json.loads(signatures)[:0]\n",
    ),
    # The halt.
    "a halted node still votes": (
        "                if self._is_halted():\n"
        "                    return False\n",
        "",
    ),
    "a halted node still logs": (
        "                if self._is_halted():\n"
        "                    raise VoteStoreError(\"NODE HAS HALTED\")\n",
        "",
    ),
    "any two certificates are a proof": (
        "        if not _is_halt_proof(self.committee, first, second):\n"
        "            raise ValueError(\"NOT A PROOF OF A HALT\")\n",
        "",
    ),
    "proof with an invalid first certificate": (
        "        first.verify(committee)\n"
        "        and second.verify(committee)\n",
        "        second.verify(committee)\n",
    ),
    "proof with an invalid second certificate": (
        "        first.verify(committee)\n"
        "        and second.verify(committee)\n",
        "        first.verify(committee)\n",
    ),
    "proof across senders": (
        "        and first.event.sender == second.event.sender\n",
        "",
    ),
    "proof across nonces": (
        "        and first.event.nonce == second.event.nonce\n",
        "",
    ),
    "the same certificate twice is a proof": (
        "        and first.event.canonical() != second.event.canonical()\n",
        "",
    ),
    "proof in the order of arrival": (
        "        low, high = sorted(\n"
        "            (first, second),\n"
        "            key=lambda certificate: certificate.event.canonical(),\n"
        "        )\n",
        "        low, high = first, second\n",
    ),
    "a later proof replaces the first": (
        "                    INSERT OR IGNORE INTO halt (\n",
        "                    INSERT OR REPLACE INTO halt (\n",
    ),
    "halt not committed": (
        "                        _encode_signatures(high),\n"
        "                    ),\n"
        "                )\n"
        "                self._commit()\n",
        "                        _encode_signatures(high),\n"
        "                    ),\n"
        "                )\n",
    ),
    "failed write of the halt ignored": (
        "                raise VoteStoreError(f\"HALT NOT RECORDED: {error}\") from error\n",
        "                return\n",
    ),
    "altered proof not checked at opening": (
        "            self._check_halt_proof()\n",
        "",
    ),
    "altered proof believed at opening": (
        "        if proof is not None and not _is_halt_proof(self.committee, *proof):\n"
        "            raise VoteStoreError(\"HALT PROOF DOES NOT VERIFY\")\n",
        "",
    ),
    "unreadable proof raises something else": (
        "        except (ValueError, KeyError, TypeError, RecursionError) as error:\n"
        "            raise VoteStoreError(\"HALT PROOF IS UNREADABLE\") from error\n",
        "        except RecursionError as error:\n"
        "            raise VoteStoreError(\"HALT PROOF IS UNREADABLE\") from error\n",
    ),
}


def test_the_tests_pass_on_the_real_source():
    result = run_tests_on(MODULE, SOURCE, TESTS)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("name", MUTATIONS)
def test_mutation_is_detected(name):
    old, new = MUTATIONS[name]
    assert SOURCE.count(old) == 1, name
    result = run_tests_on(MODULE, SOURCE.replace(old, new), TESTS)
    assert result.returncode == 1, result.stdout + result.stderr
