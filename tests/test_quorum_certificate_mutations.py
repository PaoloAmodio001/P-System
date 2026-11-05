"""The tests of tests/test_quorum_certificate.py must be able to fail.

These replace the mutations of phase 5.1, whose script was lost with /tmp on 2026-11-04.
The counts of that time are not reused: only this file counts.

Each mutation breaks one rule of core/attestation.py. Nothing here starts a process, so
every test of that file can see every mutation.

Not here on purpose: removing `self.f < 0`. It changes nothing but the text of the error,
because a negative `f` also fails the check on the size: no tuple has length `3f + 1`.
"""

from pathlib import Path

import pytest

from tests.mutation_support import ROOT, run_tests_on

MODULE = "core.attestation"
SOURCE = (ROOT / "core" / "attestation.py").read_text()
TESTS = [str(Path("tests") / "test_quorum_certificate.py")]

MUTATIONS = {
    # Integers and accounts.
    "boolean accepted as an event integer": (
        "    return type(value) is int and 0 <= value <= MAX_EVENT_INTEGER\n",
        "    return isinstance(value, int) and 0 <= value <= MAX_EVENT_INTEGER\n",
    ),
    "negative event integer": (
        "    return type(value) is int and 0 <= value <= MAX_EVENT_INTEGER\n",
        "    return type(value) is int and value <= MAX_EVENT_INTEGER\n",
    ),
    "no upper bound on event integers": (
        "    return type(value) is int and 0 <= value <= MAX_EVENT_INTEGER\n",
        "    return type(value) is int and 0 <= value\n",
    ),
    "upper bound one too low": (
        "MAX_EVENT_INTEGER = 2**256 - 1\n",
        "MAX_EVENT_INTEGER = 2**256 - 2\n",
    ),
    "empty account": (
        "    if type(value) is not str or not value:\n",
        "    if type(value) is not str:\n",
    ),
    "account that is not a string": (
        "    if type(value) is not str or not value:\n",
        "    if not value:\n",
    ),
    "account that cannot be encoded": (
        "    except UnicodeEncodeError:\n"
        "        return False\n",
        "    except UnicodeEncodeError:\n"
        "        return True\n",
    ),
    # The event.
    "any value counts as an event": (
        "        isinstance(event, Transfer)\n"
        "        and _is_account(event.sender)\n",
        "        hasattr(event, 'sender')\n"
        "        and _is_account(event.sender)\n",
    ),
    "sender not checked": (
        "        and _is_account(event.sender)\n",
        "",
    ),
    "receiver not checked": (
        "        and _is_account(event.receiver)\n",
        "",
    ),
    "amount not checked": (
        "        and _is_event_integer(event.amount)\n",
        "",
    ),
    "nonce not checked": (
        "        and _is_event_integer(event.nonce)\n",
        "",
    ),
    "parents that are not a tuple": (
        "        and type(event.parents) is tuple\n",
        "",
    ),
    "parent that is not a string": (
        "            type(parent) is str and _ROOT_PATTERN.fullmatch(parent) is not None\n",
        "            _ROOT_PATTERN.fullmatch(str(parent)) is not None\n",
    ),
    "parent that only starts like an id": (
        "            type(parent) is str and _ROOT_PATTERN.fullmatch(parent) is not None\n",
        "            type(parent) is str and _ROOT_PATTERN.match(parent) is not None\n",
    ),
    # The committee.
    "fault bound of another type": (
        "        if type(self.f) is not int or self.f < 0:\n",
        "        if self.f < 0:\n",
    ),
    "committee of any size": (
        "            or len(self.members) != (5 if self.unlock else 3) * self.f + 1\n",
        "",
    ),
    "members that are not a tuple": (
        "            type(self.members) is not tuple\n"
        "            or len(self.members) != (5 if self.unlock else 3) * self.f + 1\n",
        "            len(self.members) != (5 if self.unlock else 3) * self.f + 1\n",
    ),
    "member that is not bytes": (
        "                type(member) is not bytes\n"
        "                or len(member) != ED25519_PUBLIC_KEY_SIZE\n",
        "                len(member) != ED25519_PUBLIC_KEY_SIZE\n",
    ),
    "member of any length": (
        "                type(member) is not bytes\n"
        "                or len(member) != ED25519_PUBLIC_KEY_SIZE\n",
        "                type(member) is not bytes\n",
    ),
    "members not sorted": (
        "        if list(self.members) != sorted(set(self.members)):\n",
        "        if len(set(self.members)) != len(self.members):\n",
    ),
    "members repeated": (
        "        if list(self.members) != sorted(set(self.members)):\n",
        "        if list(self.members) != sorted(self.members):\n",
    ),
    "genesis root of another type": (
        "            type(self.genesis_root) is not str\n"
        "            or _ROOT_PATTERN.fullmatch(self.genesis_root) is None\n",
        "            _ROOT_PATTERN.fullmatch(str(self.genesis_root)) is None\n",
    ),
    "genesis root of any form": (
        "            or _ROOT_PATTERN.fullmatch(self.genesis_root) is None\n",
        "",
    ),
    "create does not sort": (
        "            members=tuple(sorted(keys)),\n",
        "            members=tuple(keys),\n",
    ),
    "create takes keys of any type": (
        "        for key in keys:\n"
        "            if type(key) is not bytes:\n"
        "                raise ValueError(\"INVALID COMMITTEE MEMBER\")\n",
        "",
    ),
    "quorum of f + 1": (
        "        return (4 if self.unlock else 2) * self.f + 1\n",
        "        return self.f + 1\n",
    ),
    "committee id without f": (
        "            \"f\": self.f,\n",
        "",
    ),
    "committee id without the genesis": (
        "            \"genesis_root\": self.genesis_root,\n",
        "",
    ),
    "committee id without the members": (
        "            \"members\": [member.hex() for member in self.members],\n",
        "",
    ),
    "boolean accepted as a validator": (
        "        return type(validator) is int and 0 <= validator < self.n\n",
        "        return isinstance(validator, int) and 0 <= validator < self.n\n",
    ),
    "negative validator": (
        "        return type(validator) is int and 0 <= validator < self.n\n",
        "        return type(validator) is int and validator < self.n\n",
    ),
    "validator beyond the committee": (
        "        return type(validator) is int and 0 <= validator < self.n\n",
        "        return type(validator) is int and 0 <= validator <= self.n\n",
    ),
    # What a vote signs.
    "no domain tag": (
        "        VOTE_DOMAIN\n"
        "        + bytes.fromhex(committee.committee_id)\n",
        "        bytes.fromhex(committee.committee_id)\n",
    ),
    "no committee id": (
        "        VOTE_DOMAIN\n"
        "        + bytes.fromhex(committee.committee_id)\n",
        "        VOTE_DOMAIN\n",
    ),
    "the id is signed instead of the canonical form": (
        "        + event.canonical()\n",
        "        + event.event_id().encode()\n",
    ),
    # Votes.
    "vote on a malformed event": (
        "        if not is_well_formed_event(event):\n"
        "            raise ValueError(\"MALFORMED EVENT\")\n",
        "",
    ),
    "vote by an identity outside the committee": (
        "            raise ValueError(\"IDENTITY IS NOT A COMMITTEE MEMBER\")\n",
        "            validator = 0\n",
    ),
    "vote verified on a malformed event": (
        "        return is_well_formed_event(event) and self._verify_payload(\n",
        "        return self._verify_payload(\n",
    ),
    "validator of a vote not checked": (
        "        return committee.has_validator(self.validator) and verify_signature(\n",
        "        return verify_signature(\n",
    ),
    "signature of a vote not checked": (
        "        return committee.has_validator(self.validator) and verify_signature(\n"
        "            committee.members[self.validator],\n"
        "            self.signature,\n"
        "            payload,\n"
        "        )\n",
        "        return committee.has_validator(self.validator)\n",
    ),
    # Certificates.
    "certificate on a malformed event": (
        "        if not is_well_formed_event(self.event):\n"
        "            return False\n",
        "",
    ),
    "votes that are not a tuple": (
        "        if type(self.votes) is not tuple or not all(\n",
        "        if not all(\n",
    ),
    "votes of another type": (
        "        if type(self.votes) is not tuple or not all(\n"
        "            type(vote) is Vote for vote in self.votes\n"
        "        ):\n",
        "        if type(self.votes) is not tuple:\n",
    ),
    "signers outside the committee": (
        "        if not all(committee.has_validator(signer) for signer in signers):\n"
        "            return False\n",
        "",
    ),
    "repeated signers counted": (
        "        if len(set(signers)) != len(signers):\n"
        "            return False\n",
        "",
    ),
    "no threshold": (
        "        if len(signers) < committee.quorum:\n"
        "            return False\n",
        "",
    ),
    "threshold one too low": (
        "        if len(signers) < committee.quorum:\n",
        "        if len(signers) < committee.quorum - 1:\n",
    ),
    "threshold one too high": (
        "        if len(signers) < committee.quorum:\n",
        "        if len(signers) <= committee.quorum:\n",
    ),
    "one good signature is enough": (
        "        return all(\n"
        "            vote._verify_payload(committee, payload)\n",
        "        return any(\n"
        "            vote._verify_payload(committee, payload)\n",
    ),
    "signatures of a certificate not checked": (
        "        return all(\n"
        "            vote._verify_payload(committee, payload)\n"
        "            for vote in self.votes\n"
        "        )\n",
        "        return True\n",
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
