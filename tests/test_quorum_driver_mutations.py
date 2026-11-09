"""The tests of QuorumDriver must be able to fail. See test_quorum_halt_mutations.py."""

import pytest

from tests.test_quorum_halt_mutations import SOURCE, run_with_source

TESTS = [
    "tests/test_quorum_driver.py",
    "-q",
    "-x",
    "--no-header",
    "-p",
    "no:cacheprovider",
]

MUTATIONS = {
    "event not checked before its signature": (
        "        return is_authorized_transfer(signed)\n",
        "        return signed.verify() and signed.identity_id == signed.transfer.sender\n",
    ),
    "signature of the sender not checked": (
        "        return is_authorized_transfer(signed)\n",
        "        return is_well_formed_event(signed.transfer) and signed.identity_id == signed.transfer.sender\n",
    ),
    "sender not tied to the signer": (
        "        return is_authorized_transfer(signed)\n",
        "        return is_well_formed_event(signed.transfer) and signed.verify()\n",
    ),
    "vote request not authorized": (
        "        if not self._is_authorized(signed):\n"
        "            self._cost += BAD_SIGNATURE_COST\n",
        "        if False:\n"
        "            self._cost += BAD_SIGNATURE_COST\n",
    ),
    "submit not authorized": (
        "        if not self._is_authorized(signed):\n"
        "            return _NOTHING\n"
        "\n"
        "        self._record_signed(signed)\n"
        "        event = signed.transfer\n",
        "        self._record_signed(signed)\n"
        "        event = signed.transfer\n",
    ),
    "submit works after a halt": (
        "        if self.halted or not self._is_admitted(signed.transfer):\n",
        "        if not self._is_admitted(signed.transfer):\n",
    ),
    "proof of equivocation not recorded": (
        "        # Before the replica, because a vote refused is when the proof appears.\n"
        "        self._record_signed(signed)\n",
        "",
    ),
    "later proof of equivocation replaces the first": (
        "            and key not in self.equivocations\n",
        "",
    ),
    "same event counts as equivocation": (
        "            first.transfer.canonical() != event.canonical()\n"
        "            and key not in self.equivocations\n",
        "            key not in self.equivocations\n",
    ),
    "submit asks even when its own vote is refused": (
        "        vote = self.replica.handle_vote_request(event, signed, gathering=True)\n"
        "\n"
        "        if vote is None:\n"
        "            return _NOTHING\n"
        "\n"
        "        _, votes = self._aggregating",
        "        vote = self.replica.handle_vote_request(event, signed, gathering=True)\n"
        "\n"
        "        if vote is None:\n"
        "            return DriverOutput(broadcasts=(encode_vote_request(signed),))\n"
        "\n"
        "        _, votes = self._aggregating",
    ),
    "own vote not counted": (
        "        votes[vote.validator] = vote\n"
        "        certificate = self._complete(event, votes)\n"
        "\n"
        "        if certificate is not None:\n",
        "        certificate = self._complete(event, votes)\n"
        "\n"
        "        if certificate is not None:\n",
    ),
    "known certificate not sent again": (
        "        if known is not None and known.event.canonical() == event.canonical():\n"
        "            return DriverOutput(broadcasts=(encode_certificate(known),))\n",
        "",
    ),
    "vote for an event not submitted here counts": (
        "        aggregating = self._aggregating.get(event.canonical())\n",
        "        aggregating = self._aggregating.setdefault(\n"
        "            event.canonical(), (event, {})\n"
        "        )\n",
    ),
    "votes collected after a halt": (
        "            self._aggregating.clear()\n",
        "",
    ),
    "buffer kept after a halt": (
        "            self._buffer.clear()\n"
        "            self._waiting.clear()\n",
        "",
    ),
    "same validator counted again": (
        "        votes[vote.validator] = vote\n"
        "        certificate = self._complete(event, votes)\n"
        "\n"
        "        if certificate is None:\n",
        "        votes[len(votes) + 100] = vote\n"
        "        certificate = self._complete(event, votes)\n"
        "\n"
        "        if certificate is None:\n",
    ),
    "signature of a vote not checked": (
        "        if not vote.verify(self.committee, event):\n",
        "        if False:\n",
    ),
    "certificate made below the quorum": (
        "        if len(votes) < self.committee.quorum:\n",
        "        if len(votes) < self.committee.quorum - 1:\n",
    ),
    "certificate made more than once": (
        "        del self._aggregating[event.canonical()]\n",
        "",
    ),
    "signers not in order": (
        "            tuple(votes[validator] for validator in sorted(votes)),\n",
        "            tuple(votes.values()),\n",
    ),
    "new certificate not executed here": (
        "        self._accept(certificate)\n"
        "        return certificate\n",
        "        return certificate\n",
    ),
    "certificate not verified": (
        "        if self.replica.certificate_is_valid(certificate):\n"
        "            self._accept(certificate)\n",
        "        if True:\n"
        "            self._accept(certificate)\n",
    ),
    "certificate handled after a halt": (
        "    def _handle_certificate(self, certificate: QuorumCertificate) -> DriverOutput:\n"
        "        if self.halted:\n"
        "            return _NOTHING\n",
        "    def _handle_certificate(self, certificate: QuorumCertificate) -> DriverOutput:\n",
    ),
    "conflict does not halt": (
        "            self.replica.record_halt(known, certificate)\n",
        "",
    ),
    "same event counts as a conflict": (
        "        if known is not None and known.event.canonical() != event.canonical():\n",
        "        if known is not None:\n",
    ),
    "certificate not remembered, so no conflict with the buffer": (
        "            event_id = event.event_id()\n"
        "            self._known[key] = certificate\n",
        "            event_id = event.event_id()\n",
    ),
    "log not remembered after a restart": (
        "            for certificate in replica.log\n",
        "            for certificate in []\n",
    ),
    "buffer tried only once": (
        "            if following is not None:\n"
        "                heapq.heappush(ready, following)\n",
        "",
    ),
    "one that could not run is not tried again": (
        "            for waiting in blocked:\n"
        "                heapq.heappush(ready, waiting)\n",
        "",
    ),
    "buffer not tried in order of id": (
        "            event_id = heapq.heappop(ready)\n",
        "            event_id = ready.pop()\n",
    ),
    "certificate leaves the buffer before it is written": (
        "            certificate = self._buffer[event_id]\n"
        "\n"
        "            if not self.replica.handle_certificate(certificate):\n",
        "            certificate = self._buffer[event_id]\n"
        "            self._no_longer_waiting(event_id)\n"
        "            self._buffer[event_id] = certificate\n"
        "            self._waiting.setdefault(certificate.event.sender, {})[certificate.event.nonce] = event_id\n"
        "            del self._buffer[event_id]\n"
        "            del self._waiting[certificate.event.sender]\n"
        "            if not self.replica.handle_certificate(certificate):\n",
    ),
    "buffer not tried on a repeated certificate": (
        "            self._waiting.setdefault(event.sender, {})[event.nonce] = event_id\n"
        "\n"
        "        self._retry_buffer()\n",
        "            self._waiting.setdefault(event.sender, {})[event.nonce] = event_id\n"
        "            self._retry_buffer()\n",
    ),
    "malformed message ignored": (
        '        raise ValueError("NOT A QUORUM MESSAGE")\n',
        "        return _NOTHING\n",
    ),
}


def test_the_tests_pass_on_the_real_source():
    result = run_with_source(SOURCE, TESTS)
    assert result.returncode == 0, result.stdout


@pytest.mark.parametrize("name", MUTATIONS)
def test_mutation_is_detected(name):
    old, new = MUTATIONS[name]
    assert SOURCE.count(old) == 1, name

    result = run_with_source(SOURCE.replace(old, new), TESTS)

    assert result.returncode == 1, result.stdout + result.stderr
