"""The tests of tests/test_quorum_epochs.py must be able to fail.

Not here on purpose: the check in `_handle_epoch_closure` that a closure continues the epoch in
force. `verify` refuses such a closure anyway, through its order of governance: that check only
avoids verifying signatures for nothing.
"""

from pathlib import Path

import pytest

from tests.mutation_support import ROOT, run_tests_on

TESTS = [str(Path("tests") / "test_quorum_epochs.py")]
SOURCES = {
    "core.attestation": (ROOT / "core" / "attestation.py").read_text(),
    "network.quorum": (ROOT / "network" / "quorum.py").read_text(),
}

IN_ATTESTATION = {
    "one key can be governance": (
        "            or self.threshold < 2\n",
        "            or self.threshold < 1\n",
    ),
    "threshold above the members": (
        "            or self.threshold > len(self.members)\n",
        "",
    ),
    "change for any committee": (
        "        if self.previous_id != current.committee_id:\n"
        "            return False\n",
        "",
    ),
    "change to an invalid committee": (
        "        try:\n"
        "            self.next_committee(current)\n"
        "        except ValueError:\n"
        "            return False\n",
        "",
    ),
    "repeated governance signer": (
        "            len(set(indexes)) != len(indexes)\n"
        "            or len(indexes) < governance.threshold\n",
        "            len(indexes) < governance.threshold\n",
    ),
    "no governance threshold": (
        "            or len(indexes) < governance.threshold\n",
        "",
    ),
    "governance signature not checked": (
        "        return all(\n"
        "            verify_signature(governance.members[index], signature, payload)\n"
        "            for index, signature in self.signatures\n"
        "        )\n",
        "        return True\n",
    ),
    "report with votes in any order": (
        "            and list(self.votes)\n"
        "            == sorted(self.votes, key=lambda signed: signed.transfer.canonical())\n",
        "",
    ),
    "report with events nobody signed": (
        "            and all(is_good(signed) for signed in self.votes)\n",
        "",
    ),
    "signer of an event need not be its sender": (
        "        and signed.identity_id == account_owner(signed.transfer.sender)\n",
        "",
    ),
    "report signature not checked": (
        "            and verify_signature(\n"
        "                committee.members[self.validator],\n"
        "                self.signature,\n"
        "                self._payload(committee, change_id, self.votes),\n"
        "            )\n",
        "",
    ),
    "report not bound to the change": (
        "            + bytes.fromhex(change_id)\n",
        "",
    ),
    "report not bound to the votes": (
        "        return cls._payload_of_digest(committee, change_id, _votes_digest(votes))\n",
        "        return cls._payload_of_digest(committee, change_id, b\"\")\n",
    ),
    "certificate of any epoch": (
        "        if type(self.epoch) is not int or self.epoch != committee.epoch:\n"
        "            return False\n",
        "",
    ),
    "same id for the next committee": (
        "        if self.epoch > 0:\n"
        "            data[\"epoch\"] = self.epoch\n"
        "            data[\"previous\"] = self.previous_id\n",
        "",
    ),
    "guilty members from one certificate": (
        "    common = {vote.validator for vote in first.votes} & {\n"
        "        vote.validator for vote in second.votes\n"
        "    }\n",
        "    common = {vote.validator for vote in first.votes}\n",
    ),
}

IN_QUORUM = {
    "non member refused no more": (
        "        if committee.index_of(validator) is None and not joining:\n",
        "        if False:\n",
    ),
    "closed epoch still votes": (
        "                if self._is_closed(epoch):\n"
        "                    return False\n",
        "",
    ),
    "locks ignored": (
        "                if self._is_locked_against(event, canonical):\n"
        "                    return False\n",
        "",
    ),
    "a lock also blocks its own event": (
        "            row[0] != canonical\n",
        "            True\n",
    ),
    "closing not durable": (
        "                    (epoch, change.change_id, _change_text(change)),\n"
        "                )\n"
        "                self._commit()\n"
        "            except sqlite3.Error as error:\n"
        "                raise VoteStoreError(f\"EPOCH NOT CLOSED: {error}\") from error\n",
        "                    (epoch, change.change_id, _change_text(change)),\n"
        "                )\n"
        "            except sqlite3.Error as error:\n"
        "                raise VoteStoreError(f\"EPOCH NOT CLOSED: {error}\") from error\n",
    ),
    "votes with no proof reported anyway": (
        "                if any(row[1] is None for row in rows):\n"
        "                    raise VoteStoreError(\"A VOTE HAS NO PROOF OF ITS SENDER: CANNOT REPORT\")\n",
        "                rows = [row for row in rows if row[1] is not None]\n",
    ),
    "locks not installed": (
        "                self._add_locks(locks)\n"
        "                # Votes signed for the committee that ended, which the driver forgets as well.\n",
        "                # Votes signed for the committee that ended, which the driver forgets as well.\n",
    ),
    "committee not changed in memory": (
        "            self.committee = following\n"
        "            self._chain[following.epoch] = following\n",
        "",
    ),
    "closure not checked at opening": (
        "            if not closure.verify(self.governance, self.committee):\n"
        "                raise VoteStoreError(\"CLOSURE DOES NOT VERIFY\")\n",
        "",
    ),
    "opening without governance": (
        "            if self.governance is None:\n"
        "                raise VoteStoreError(\"THIS STORE HAS EPOCHS: GOVERNANCE IS REQUIRED\")\n",
        "            if self.governance is None:\n"
        "                continue\n",
    ),
    "non member votes": (
        "        if not self.is_member:\n"
        "            return None\n"
        "\n"
        "        # Lean spec (formal/lean/PSystem/Quorum.lean, voteRequest): vote is admitted\n",
        "        # Lean spec (formal/lean/PSystem/Quorum.lean, voteRequest): vote is admitted\n",
    ),
    "proposal not checked": (
        "            or self.halted\n"
        "            or not change.verify(self.governance, self.committee)\n"
        "        ):\n"
        "            return _NOTHING\n"
        "\n"
        "        self._change = change\n",
        "            or self.halted\n"
        "        ):\n"
        "            return _NOTHING\n"
        "\n"
        "        self._change = change\n",
    ),
    "closure not checked": (
        "        if not closure.verify(self.governance, self.committee):\n"
        "            self._cost += BAD_SIGNATURE_COST\n"
        "            return _NOTHING\n",
        "",
    ),
    "no closure in an answer": (
        "            for closure in self.replica.closures(epoch)\n",
        "            for closure in ()\n",
    ),
    "all closures in every answer": (
        "            for closure in self.replica.closures(epoch)\n",
        "            for closure in self.replica.closures(0)\n",
    ),
    "certificates made without their epoch": (
        "            tuple(votes[validator] for validator in sorted(votes)),\n"
        "            self.committee.epoch,\n"
        "        )\n"
        "        self._accept(certificate)\n",
        "            tuple(votes[validator] for validator in sorted(votes)),\n"
        "        )\n"
        "        self._accept(certificate)\n",
    ),
    "vote kept without its proof": (
        "        vote = self.replica.handle_vote_request(signed.transfer, signed)\n",
        "        vote = self.replica.handle_vote_request(signed.transfer)\n",
    ),
}


def test_the_tests_pass_on_the_real_source():
    result = run_tests_on("network.quorum", SOURCES["network.quorum"], TESTS)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("name", IN_ATTESTATION)
def test_mutation_in_attestation_is_detected(name):
    old, new = IN_ATTESTATION[name]
    source = SOURCES["core.attestation"]
    assert source.count(old) == 1, name
    result = run_tests_on("core.attestation", source.replace(old, new), TESTS)
    assert result.returncode == 1, result.stdout + result.stderr


@pytest.mark.parametrize("name", IN_QUORUM)
def test_mutation_in_quorum_is_detected(name):
    old, new = IN_QUORUM[name]
    source = SOURCES["network.quorum"]
    assert source.count(old) == 1, name
    result = run_tests_on("network.quorum", source.replace(old, new), TESTS)
    assert result.returncode == 1, result.stdout + result.stderr
