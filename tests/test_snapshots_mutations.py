"""The tests of tests/test_snapshots.py must be able to fail.

Each mutation breaks one rule of a snapshot, of what a member signs, of what a node takes from
others, or of pruning. The test with real nodes stays out: each process imports the module as it is,
and it takes seconds. Nothing here reads the floors of the differential, which has its own mutations
in tests/test_epoch_differential_mutations.py.

Not here on purpose:
- the order of `sorted(self._snapshot_votes)`: signers are compared as a set.
- the `LOG.info` of a snapshot taken: nothing depends on it.
- the check that a member is behind, before it derives: the digest would say the same, and it only
  saves a pass over the log for each request sent again.
"""

from pathlib import Path

import pytest

from tests.mutation_support import ROOT, run_tests_on

TESTS = [str(Path("tests") / "test_snapshots.py"), "-k", "not real_nodes"]

ATTESTATION = {
    "signature not checked": (
        "        return all(is_signed_lock(signed) for signed in self.locks) and verify_signature(\n"
        "            committee.members[self.validator],\n"
        "            self.signature,\n"
        "            self._payload(committee, digest, self.locks),\n"
        "        )\n",
        "        return all(is_signed_lock(signed) for signed in self.locks)\n",
    ),
    "signature without the locks": (
        "            + bytes.fromhex(digest)\n"
        "            + _votes_digest(locks)\n",
        "            + bytes.fromhex(digest)\n",
    ),
    "signature without the committee": (
        "            SNAPSHOT_DOMAIN\n"
        "            + bytes.fromhex(committee.committee_id)\n",
        "            SNAPSHOT_DOMAIN\n",
    ),
    "signature without the digest": (
        "            + bytes.fromhex(digest)\n"
        "            + _votes_digest(locks)\n",
        "            + _votes_digest(locks)\n",
    ),
    "digest without the state": (
        "        return sha256(bytes.fromhex(self.state.root()) + ids.digest()).hexdigest()\n",
        "        return ids.hexdigest()\n",
    ),
    "digest without the ids": (
        "        return sha256(bytes.fromhex(self.state.root()) + ids.digest()).hexdigest()\n",
        "        return sha256(bytes.fromhex(self.state.root())).hexdigest()\n",
    ),
    "no quorum": (
        "        if len(set(signers)) != len(signers) or len(signers) < committee.quorum:\n",
        "        if len(set(signers)) != len(signers):\n",
    ),
    "a repeated signer counts": (
        "        if len(set(signers)) != len(signers) or len(signers) < committee.quorum:\n",
        "        if len(signers) < committee.quorum:\n",
    ),
    "one good signature is enough": (
        "        return all(\n            attestation.verify(committee, self.digest, checked, allow_legacy)\n",
        "        return any(\n            attestation.verify(committee, self.digest, checked, allow_legacy)\n",
    ),
    "any epoch": (
        "        if type(self.epoch) is not int or self.epoch != committee.epoch or not self.has_ordered_ids():\n",
        "        if type(self.epoch) is not int or not self.has_ordered_ids():\n",
    ),
    "ids in any order": (
        "        if type(self.epoch) is not int or self.epoch != committee.epoch or not self.has_ordered_ids():\n",
        "        if type(self.epoch) is not int or self.epoch != committee.epoch:\n",
    ),
    "ids may repeat": (
        "            and list(self.ids) == sorted(set(self.ids))\n",
        "            and list(self.ids) == sorted(self.ids)\n",
    ),
    "the locks of one signer only": (
        "        for attestation in self.attestations:\n"
        "            if attestation.version != SNAPSHOT_ATTESTATION_VERSION:\n",
        "        for attestation in self.attestations[:1]:\n"
        "            if attestation.version != SNAPSHOT_ATTESTATION_VERSION:\n",
    ),
    "the signer of a vote is whoever": (
        '        if validator is None:\n            raise ValueError("SIGNER IS NOT A COMMITTEE MEMBER")\n',
        "        validator = validator or 0\n",
    ),
}

QUORUM = {
    # A restart.
    "snapshot believed at opening": (
        '            if not self._snapshot_is_good(self.base, allow_legacy=True):\n                raise VoteStoreError("SNAPSHOT DOES NOT VERIFY")\n',
        "",
    ),
    "state not taken from the snapshot": (
        "            self.state = self.base.state.copy()\n            self._executed_ids = set(self.base.ids)\n",
        "            self._executed_ids = set(self.base.ids)\n",
    ),
    "ids not taken from the snapshot": (
        "            self.state = self.base.state.copy()\n            self._executed_ids = set(self.base.ids)\n",
        "            self.state = self.base.state.copy()\n",
    ),
    "covered rows read like the others": (
        "            if self.is_covered(certificate.event):\n"
        "                if certificate.event.event_id() not in self._executed_ids:\n",
        "            if False:\n"
        "                if certificate.event.event_id() not in self._executed_ids:\n",
    ),
    "a covered row not checked against the ids": (
        '                if certificate.event.event_id() not in self._executed_ids:\n                    raise VoteStoreError("LOG OF CERTIFICATES DOES NOT FIT THE SNAPSHOT")\n',
        "",
    ),
    "a covered row left out of the log": (
        "                self.log.append(certificate)\n                continue\n",
        "                continue\n",
    ),
    "unreadable snapshot raises something else": (
        '        except (ValueError, KeyError, TypeError, RecursionError) as error:\n            raise VoteStoreError("SNAPSHOT IS UNREADABLE") from error\n',
        '        except ZeroDivisionError as error:\n            raise VoteStoreError("SNAPSHOT IS UNREADABLE") from error\n',
    ),
    # What a member signs.
    "a member signs without deriving": (
        "            or not self._derives_snapshot(digest, nonces)\n",
        "",
    ),
    "any epoch signed": (
        "            or epoch != self.committee.epoch\n            or not self._derives_snapshot(digest, nonces)\n",
        "            or not self._derives_snapshot(digest, nonces)\n",
    ),
    "not a member signs": (
        "            not self.is_member\n            or self._store.halted()\n            or epoch != self.committee.epoch\n",
        "            self._store.halted()\n            or epoch != self.committee.epoch\n",
    ),
    "a halted member signs": (
        "            not self.is_member\n            or self._store.halted()\n            or epoch != self.committee.epoch\n",
        "            not self.is_member\n            or epoch != self.committee.epoch\n",
    ),
    "the digest of the state is not compared": (
        "        return Snapshot(self.committee.epoch, state, tuple(sorted(ids))).digest == digest\n",
        "        return True\n",
    ),
    "one pass over the log": (
        "        while pending and progress:\n            progress = False\n",
        "        for _once in [0]:\n            progress = False\n",
    ),
    "a parent not checked when deriving": (
        "            event.event_id() not in ids\n            and set(event.parents) <= ids\n",
        "            event.event_id() not in ids\n",
    ),
    # What a node takes.
    "a snapshot of an ended committee is taken": (
        "            snapshot.epoch != self.committee.epoch\n            or not self._snapshot_is_good(snapshot)\n",
        "            not self._snapshot_is_good(snapshot)\n",
    ),
    "a snapshot believed": (
        "            snapshot.epoch != self.committee.epoch\n            or not self._snapshot_is_good(snapshot)\n",
        "            snapshot.epoch != self.committee.epoch\n",
    ),
    "the count of the ids not compared": (
        "            and len(snapshot.ids)\n            == sum(snapshot.state.nonces.values()) - sum(self._initial_state.nonces.values())\n",
        "",
    ),
    "an older snapshot taken": (
        "                    snapshot.floor(sender) < nonce\n",
        "                    False and snapshot.floor(sender) < nonce\n",
    ),
    "the same snapshot is news": (
        "                and self.base.digest == snapshot.digest\n                and self.base.epoch == snapshot.epoch\n                and not self.base.is_legacy\n",
        "                and False\n",
    ),
    "a missing event believed": (
        "                if event.event_id() in ids:\n                    continue\n",
        "                continue\n",
    ),
    "a log that does not run believed": (
        "            if not self._runs_on(state, ids, event):\n                LOG.critical(\n                    \"the log of this node does not run after a snapshot\",\n",
        "            if False:\n                LOG.critical(\n                    \"the log of this node does not run after a snapshot\",\n",
    ),
    "the log is not run after the snapshot": (
        "            StateDeriver._apply_one(state, event)\n            ids.add(event.event_id())\n\n        self._store.record_snapshot(snapshot)\n",
        "        self._store.record_snapshot(snapshot)\n",
    ),
    "not on disk": (
        "        self._store.record_snapshot(snapshot)\n        self.base = snapshot\n",
        "        self.base = snapshot\n",
    ),
    "the state stays": (
        "        self.base = snapshot\n        self.state = state\n",
        "        self.base = snapshot\n",
    ),
    "the ids stay": (
        "        self.state = state\n        self._executed_ids = ids\n",
        "        self.state = state\n",
    ),
    # Pruning.
    "pruned in memory only": (
        "            self._store.forget_certificates([c.event.event_id() for c in covered])\n",
        "",
    ),
    "pruned on disk only": (
        "            self.log = [c for c in self.log if not self.is_covered(c.event)]\n",
        "",
    ),
    "prunes everything": (
        "        covered = [c for c in self.log if self.is_covered(c.event)]\n",
        "        covered = list(self.log)\n",
    ),
    "prunes with the setting off": (
        "        if self.prune:\n            for certificate in replica.prune_covered():\n",
        "        if True:\n            for certificate in replica.prune_covered():\n",
    ),
    "never prunes": (
        "        if self.prune:\n            for certificate in replica.prune_covered():\n",
        "        if False:\n            for certificate in replica.prune_covered():\n",
    ),
    "the buffer keeps what the snapshot covers": (
        "            if replica.is_covered(certificate.event):\n                self._no_longer_waiting(event_id)\n",
        "            pass\n",
    ),
    "the buffer is not tried": (
        "                self._no_longer_waiting(event_id)\n\n        self._retry_buffer()\n        return True\n",
        "                self._no_longer_waiting(event_id)\n\n        return True\n",
    ),
    "the index of the log stays": (
        "        self._log_by_sender = {}\n        self._indexed = 0\n\n        # What was waiting",
        "        # What was waiting",
    ),
    # The floor.
    "a vote under the floor": (
        "                if self._is_below_floor(event):\n                    return False\n",
        "",
    ),
    "a vote at the floor refused": (
        "        return row is not None and event.nonce < int(row[0])\n",
        "        return row is not None and event.nonce <= int(row[0])\n",
    ),
    "the floor of anyone": (
        '            "SELECT nonce FROM floors WHERE sender = ?",\n            (event.sender,),\n',
        '            "SELECT nonce FROM floors WHERE ? != \'\'",\n            (event.sender,),\n',
    ),
    "floor not written": (
        '                self._connection.executemany(\n                    "INSERT OR REPLACE INTO floors (sender, nonce) VALUES (?, ?)",\n                    [(sender, str(nonce)) for sender, nonce in snapshot.state.nonces.items()],\n                )\n',
        "",
    ),
    "locks not removed": (
        '                self._connection.executemany(\n                    "DELETE FROM locks WHERE sender = ? AND nonce = ?",\n                    stale,\n                )\n',
        "",
    ),
    "locks over the floor removed": (
        "                    if int(nonce) < snapshot.floor(sender)\n",
        "                    if True\n",
    ),
    "old votes stay": (
        '                for table in ("votes", "vote_evidence", "report_locks"):\n                    self._connection.execute(f"DELETE FROM {table} WHERE epoch < ?", (epoch,))\n',
        "",
    ),
    "votes of this epoch go": (
        '                    self._connection.execute(f"DELETE FROM {table} WHERE epoch < ?", (epoch,))\n',
        '                    self._connection.execute(f"DELETE FROM {table} WHERE epoch <= ?", (epoch,))\n',
    ),
    "floor at any time": (
        "        self._snapshot_votes = {}\n\n        if self.prune:\n            self.replica.apply_floor()\n",
        "        self._snapshot_votes = {}\n\n        if True:\n            self.replica.apply_floor()\n",
    ),
    "no floor at a new epoch": (
        "        if self.prune:\n            self.replica.apply_floor()\n",
        "",
    ),
    "signer gives all its locks": (
        "        kept = [row for row in rows if int(row[1]) >= nonces.get(row[0], 0)]\n",
        "        kept = rows\n",
    ),
    "locks of the signers not kept": (
        "                self._add_locks(snapshot.locks())\n",
        "",
    ),
    # The driver.
    "a certificate under the snapshot goes in the buffer": (
        "        if known is None and self.replica.is_covered(event):\n",
        "        if False:\n",
    ),
    "a conflict with the snapshot is not reported": (
        '            if not self.replica.has_executed_id(event.event_id()):\n                LOG.critical(\n                    "valid certificate conflicts with a snapshot",\n',
        '            if False:\n                LOG.critical(\n                    "valid certificate conflicts with a snapshot",\n',
    ),
    "a pruned certificate costs a signature": (
        "            if self.replica.is_covered(event) and self.replica.has_executed_id(event.event_id()):\n                continue\n",
        "",
    ),
    "vote of another digest counted": (
        "            or digest != candidate.digest\n            or candidate.epoch != self.committee.epoch\n",
        "            or candidate.epoch != self.committee.epoch\n",
    ),
    "vote not verified": (
        "        if not attestation.verify(self.committee, digest):\n            self._cost += BAD_SIGNATURE_COST\n            return _NOTHING\n",
        "",
    ),
    "a quorum of one": (
        "        if len(self._snapshot_votes) < self.committee.quorum:\n",
        "        if len(self._snapshot_votes) < 1:\n",
    ),
    "votes of nothing asked": (
        "            candidate is None\n            or digest != candidate.digest\n            or candidate.epoch",
        "            digest != getattr(candidate, 'digest', digest)\n            or candidate.epoch",
    ),
    "the proposer does not keep it": (
        "        self._take_snapshot(snapshot)\n        return DriverOutput(broadcasts=(encode_snapshot(snapshot),))\n",
        "        return DriverOutput(broadcasts=(encode_snapshot(snapshot),))\n",
    ),
    "the proposer does not send it": (
        "        self._take_snapshot(snapshot)\n        return DriverOutput(broadcasts=(encode_snapshot(snapshot),))\n",
        "        self._take_snapshot(snapshot)\n        return _NOTHING\n",
    ),
    "no request after taking one": (
        "        request = self.sync_request()\n        return _NOTHING if request is None else DriverOutput(replies=(request,))\n\n    def _take_snapshot",
        "        return _NOTHING\n\n    def _take_snapshot",
    ),
    "asks with the setting off": (
        "        if self.snapshot_every is None or self.halted:\n",
        "        if self.halted:\n",
    ),
    "a halted node asks": (
        "        if self.snapshot_every is None or self.halted:\n",
        "        if self.snapshot_every is None:\n",
    ),
    "never asks again": (
        "            return DriverOutput(broadcasts=(self._snapshot_request(),))\n\n        self._snapshot = None\n",
        "            return _NOTHING\n\n        self._snapshot = None\n",
    ),
    "asks for one snapshot for ever": (
        "            self._snapshot is not None\n            and self._clock() - self._snapshot_started < self.SNAPSHOT_ASK_SECONDS\n",
        "            self._snapshot is not None\n",
    ),
    "all members start together": (
        "self.snapshot_every * (1 + index / self.committee.n)",
        "self.snapshot_every",
    ),
    "asks however few the events": (
        "        if replica.executed_since_base() >= self.snapshot_every * (1 + index / self.committee.n):\n",
        "        if True:\n",
    ),
    "not a new signature after a change": (
        "        return (\n            self.prune\n            and replica.base is not None\n            and (replica.base.epoch != self.committee.epoch or replica.base.is_legacy)\n        )\n",
        "        return False\n",
    ),
    "not a member asks": (
        "        if index is None:\n            return False\n\n        # A snapshot by another member",
        "        index = index or 0\n\n        # A snapshot by another member",
    ),
    # Serving others.
    "the snapshot is not served": (
        "        snapshot = self._snapshot_for(frontier)\n",
        "        snapshot = ()\n",
    ),
    "the snapshot is always served": (
        "                if count != floor - needed:\n",
        "                if True:\n",
    ),
    "only the start of a log is checked": (
        "                if count != floor - needed:\n",
        "                if not held or held[0].event.nonce > needed:\n",
    ),
    "the frontier leaves out what the snapshot gave": (
        "        if self.replica.base is not None:\n            frontier.update(\n",
        "        if False:\n            frontier.update(\n",
    ),
    "a position taken for a nonce": (
        "            start = bisect_left(\n"
        "                certificates,\n"
        "                frontier.get(sender, 0),\n"
        "                key=lambda certificate: certificate.event.nonce,\n"
        "            )\n",
        "            start = frontier.get(sender, 0)\n",
    ),
}

SOURCES = {
    "core.attestation": (ROOT / "core" / "attestation.py").read_text(),
    "network.quorum": (ROOT / "network" / "quorum.py").read_text(),
}


@pytest.mark.parametrize("module", SOURCES)
def test_the_tests_pass_on_the_real_source(module):
    result = run_tests_on(module, SOURCES[module], TESTS)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("name", ATTESTATION)
def test_mutation_of_the_value_is_detected(name):
    old, new = ATTESTATION[name]
    source = SOURCES["core.attestation"]
    assert source.count(old) == 1, name
    result = run_tests_on("core.attestation", source.replace(old, new), TESTS)
    assert result.returncode == 1, result.stdout + result.stderr


@pytest.mark.parametrize("name", QUORUM)
def test_mutation_of_the_protocol_is_detected(name):
    old, new = QUORUM[name]
    source = SOURCES["network.quorum"]
    assert source.count(old) == 1, name
    result = run_tests_on("network.quorum", source.replace(old, new), TESTS)
    assert result.returncode == 1, result.stdout + result.stderr
