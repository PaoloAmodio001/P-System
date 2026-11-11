"""The tests of tests/test_snapshot_signed_locks.py must be able to fail.

Each mutation takes away one part of the rule that a lock in a snapshot is signed by its sender, or of
the migration of the store to schema 6.

Not here on purpose: the choice of the smallest signature for one event in `Snapshot.locks`. Ed25519
gives one signature for one key and one message, so the tests cannot build two.
"""

from pathlib import Path

import pytest

from tests.mutation_support import ROOT, quorum_source, run_tests_on

TESTS = [
    str(Path("tests") / "test_snapshot_signed_locks.py"),
    str(Path("tests") / "test_snapshots.py"),
    "-k",
    "not real_nodes",
]

MUTATIONS = {
    "core.attestation": {
        "a lock not signed by its sender": (
            "            if not _is_signed_by_its_sender(signed):\n"
            "                return False\n"
            "\n"
            "            checked.add(signed)\n"
            "            return True\n"
            "\n"
            "        return all(is_signed_lock(signed)",
            "            checked.add(signed)\n"
            "            return True\n"
            "\n"
            "        return all(is_signed_lock(signed)",
        ),
        "a bare lock taken": (
            "            if type(signed) is not SignedTransfer or not is_well_formed_event(signed.transfer):\n",
            "            if not is_well_formed_event(getattr(signed, 'transfer', signed)):\n",
        ),
        "version 1 believed from anyone": (
            "        if self.version == 1 and allow_legacy:\n",
            "        if self.version == 1:\n",
        ),
        "a bare lock signed": (
            '        if not all(type(signed) is SignedTransfer for signed in locks):\n'
            '            raise ValueError("A LOCK CARRIES THE SIGNATURE OF ITS SENDER")\n',
            "",
        ),
    },
    "network.message": {
        "the form before version 2 read from a peer": (
            '    if legacy and type(value) is dict and "version" not in value:\n',
            '    if type(value) is dict and "version" not in value:\n',
        ),
    },
    "network.quorum": {
        "an unsigned lock left out of a snapshot": (
            "        if any(row[4] is None for row in kept):\n            return None\n",
            "        kept = [row for row in kept if row[4] is not None]\n",
        ),
        "a member with an unsigned lock signs": (
            "        if locks is None:\n"
            '            LOG.warning("a lock from an older store has no signature of its sender: no snapshot signed")\n'
            "            return None\n",
            "        locks = locks or []\n",
        ),
        "the signatures of the closures not read back": (
            "                self._sign_locks_from_closures()\n",
            "",
        ),
        "the snapshot of the file read only in the new form": (
            "            return decode_snapshot_body(json.loads(row[0]), legacy=True)\n",
            "            return decode_snapshot_body(json.loads(row[0]))\n",
        ),
        "a snapshot of version 1 served to peers": (
            "        if base is None or base.is_legacy:\n            return ()\n",
            "        if base is None:\n            return ()\n",
        ),
    },
}

PATHS = {
    "core.attestation": ROOT / "core" / "attestation.py",
    "network.message": ROOT / "network" / "message.py",
    "network.quorum": ROOT / "network" / "quorum.py",
}

CASES = [(module, name) for module, mutations in MUTATIONS.items() for name in mutations]


@pytest.mark.parametrize("module", MUTATIONS)
def test_the_tests_pass_on_the_real_source(module):
    result = run_tests_on(module, (quorum_source() if module == "network.quorum" else PATHS[module].read_text()), TESTS)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(("module", "name"), CASES)
def test_mutation_is_detected(module, name):
    old, new = MUTATIONS[module][name]
    source = (quorum_source() if module == "network.quorum" else PATHS[module].read_text())
    assert source.count(old) == 1, name
    result = run_tests_on(module, source.replace(old, new), TESTS)
    assert result.returncode == 1, result.stdout + result.stderr
