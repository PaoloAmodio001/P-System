"""The tests of the durable halt must be able to fail.

Each mutation removes one rule from the source of network/quorum.py, and the tests
of the halt must notice. The mutated source runs in a separate process, in place of
the real module, so a mutation cannot leak into another test.

Limit: the workers that the crash tests spawn import the real module, so these
mutations do not reach what runs inside them.
"""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SOURCE = (ROOT / "network" / "quorum.py").read_text()

RUNNER = """
import sys

import network.quorum
import pytest

try:
    exec(compile(sys.argv[1], "network/quorum.py", "exec"), network.quorum.__dict__)
except Exception:
    # Python exits with 1 on an uncaught exception, the same as a failing test.
    sys.exit(3)

sys.exit(pytest.main(sys.argv[2:]))
"""

TESTS = [
    "tests/test_quorum_vote_store.py",
    "tests/test_quorum_replica.py",
    "-k",
    "halt or schema or halted",
    "-q",
    "-x",
    "--no-header",
    "-p",
    "no:cacheprovider",
]

VOTE_CHECK = """                if self._is_halted():
                    return False

"""
CERTIFICATE_CHECK = """                if self._is_halted():
                    raise VoteStoreError("NODE HAS HALTED")

"""

MUTATIONS = {
    "first certificate not verified": (
        "        first.verify(committee_of(first))\n        and second.verify(committee_of(second))\n",
        "        second.verify(committee_of(second))\n",
    ),
    "second certificate not verified": (
        "        and second.verify(committee_of(second))\n",
        "",
    ),
    "sender not compared": (
        "        and first.event.sender == second.event.sender\n",
        "",
    ),
    "nonce not compared": (
        "        and first.event.nonce == second.event.nonce\n",
        "",
    ),
    "same event counts as a conflict": (
        "        and first.event.canonical() != second.event.canonical()\n",
        "",
    ),
    "proof not checked when written": (
        "        if not _is_halt_proof(self.committee_of, first, second):\n",
        "        if False:\n",
    ),
    "proof not checked when opened": (
        "        if proof is not None and not _is_halt_proof(self.committee_of, *proof):\n",
        "        if False:\n",
    ),
    "unreadable proof not turned into a store error": (
        "        except (ValueError, KeyError, TypeError, RecursionError) as error:\n"
        '            raise VoteStoreError("HALT PROOF IS UNREADABLE") from error\n',
        "        except ZeroDivisionError as error:\n"
        '            raise VoteStoreError("HALT PROOF IS UNREADABLE") from error\n',
    ),
    "recursion error not caught when opened": (
        "        except (ValueError, KeyError, TypeError, RecursionError) as error:\n"
        "            raise VoteStoreError(\"HALT PROOF IS UNREADABLE\") from error\n",
        "        except (ValueError, KeyError, TypeError) as error:\n"
        "            raise VoteStoreError(\"HALT PROOF IS UNREADABLE\") from error\n",
    ),
    "proof not checked at all on opening": (
        "            self._check_halt_proof()\n",
        "",
    ),
    "votes allowed after a halt": (VOTE_CHECK, ""),
    "certificates recorded after a halt": (CERTIFICATE_CHECK, ""),
    "replica executes after a halt": (
        "        if self._store.halted() or not self._can_execute(certificate):\n",
        "        if not self._can_execute(certificate):\n",
    ),
    "order of arrival kept": (
        "        low, high = sorted(\n"
        "            (first, second),\n"
        "            key=lambda certificate: certificate.event.canonical(),\n"
        "        )\n",
        "        low, high = first, second\n",
    ),
    "second proof replaces the first": (
        "INSERT OR IGNORE INTO halt",
        "INSERT OR REPLACE INTO halt",
    ),
    "halt not committed": (
        "                        _encode_signatures(high),\n"
        "                        high.epoch,\n"
        "                    ),\n"
        "                )\n"
        "                self._commit()\n",
        "                        _encode_signatures(high),\n"
        "                        high.epoch,\n"
        "                    ),\n"
        "                )\n",
    ),
    "write failure swallowed": (
        '                raise VoteStoreError(f"HALT NOT RECORDED: {error}") from error\n',
        "                pass\n",
    ),
    "unknown version accepted": (
        "            elif version not in (_SCHEMA_VERSION, _SCHEMA_VERSION_5, _SCHEMA_VERSION_4):\n",
        "            elif False:\n",
    ),
    "version 1 refused instead of migrated": (
        "            if version == _PREVIOUS_SCHEMA_VERSION:\n",
        "            if False:\n",
    ),
    "migration does not update the version": (
        "                self._connection.execute(\n"
        "                    \"UPDATE meta SET value = ? WHERE key = 'schema_version'\",\n"
        "                    (_SCHEMA_VERSION,),\n"
        "                )\n",
        "",
    ),
    "migration not committed": (
        "                    (_SCHEMA_VERSION,),\n"
        "                )\n"
        "                self._commit()\n",
        "                    (_SCHEMA_VERSION,),\n"
        "                )\n",
    ),
    "owner not checked before migrating": (
        "            if found != expected:\n"
        '                raise VoteStoreError("VOTE STORE BELONGS TO ANOTHER VALIDATOR")\n'
        "\n"
        "            if version == _PREVIOUS_SCHEMA_VERSION:\n",
        "            if version == _PREVIOUS_SCHEMA_VERSION:\n",
    ),
}


def run_with_source(source: str, tests: list[str]) -> subprocess.CompletedProcess:
    """Run `tests` with `source` in place of network/quorum.py."""
    return subprocess.run(
        [sys.executable, "-c", RUNNER, source, *tests],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_the_tests_pass_on_the_real_source():
    # Otherwise every mutation below would look detected.
    result = run_with_source(SOURCE, TESTS)
    assert result.returncode == 0, result.stdout


@pytest.mark.parametrize("name", MUTATIONS)
def test_mutation_is_detected(name):
    old, new = MUTATIONS[name]
    # A mutation that no longer applies must not pass as detected.
    assert SOURCE.count(old) == 1, name

    result = run_with_source(SOURCE.replace(old, new), TESTS)

    # 1 is a failing test. Any other code is a mutation written wrongly.
    assert result.returncode == 1, result.stdout + result.stderr
