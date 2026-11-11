"""
Rounds in a node: what ends a split vote. formal/lean/PSystem/QuorumRounds.lean.

The rules are the compiled model (`lean_core.step`), called by the replica, which writes each new
state before anything it allows is signed. This module turns messages into inputs of the model and
new states into messages:

- a vote of round 0 of this node is the input `request`;
- a prepare certificate (`2f+1` votes of round 0, or prevotes of a later round) is `prepared`, and
  the precommit it allows is sent to every member;
- a decision (`n` votes of round 0, or `2f+1` precommits) is `fast` or `committed`, and the node
  executes it;
- when a key has waited too long in a round, `timeout`: the node reports to every member;
- the leader of a round, with `2f+1` reports, proposes what they force (`Rounds.choose`), else its
  own vote; a proposal of the leader, justified, is `proposal`, and the prevote it allows is sent.

What the model takes as given and is done here: signatures are checked before anything reaches it,
and only signers whose signature verified are passed; a proposal is taken only from the leader of
its round, since `good_round_decides` is about the proposal of an honest leader.
"""

from core.attestation import (
    PRECOMMIT,
    PREVOTE,
    VOTE,
    QuorumCertificate,
    RoundProposal,
    RoundReport,
    Vote,
    is_authorized_transfer,
    round_offset,
)
from core.event import Transfer
from core.signed_event import SignedTransfer
from network.message import (
    encode_certificate,
    encode_new_round,
    encode_proposal,
    encode_round_vote,
)
from network.quorum import lean_core
from network.quorum.common import LOG


class RoundDriver:
    """The rounds of the keys of one node. Not thread-safe: the driver serializes the calls."""

    # How long a key waits in round 0 before the first report, then twice as long in each round up to
    # the second number. Partial synchrony is the assumption that some round lasts long enough.
    ROUND_FIRST_SECONDS = 2.0
    ROUND_LONGEST_SECONDS = 60.0

    def __init__(self, driver) -> None:
        self.driver = driver
        # Versions with their sender's signature, by event id: what a proposal and a report carry.
        self.signed: dict[str, SignedTransfer] = {}
        self.events: dict[str, Transfer] = {}
        # Votes of later rounds and precommits, by key, phase, round and event.
        self.votes: dict[tuple, dict[int, Vote]] = {}
        # Reports of each round, by key and round, then by member.
        self.reports: dict[tuple, dict[int, RoundReport]] = {}
        self.proposed: set[tuple] = set()
        self.prepared: set[tuple] = set()
        # When each key entered its round, for the keys not decided.
        self.started: dict[tuple[str, int], float] = {}

        if self.enabled:
            now = self.clock()
            for sender, nonce, state in self.replica.round_states():
                if state["decided"] is None:
                    self.started[(sender, nonce)] = now

    @property
    def replica(self):
        return self.driver.replica

    @property
    def committee(self):
        return self.replica.committee

    @property
    def enabled(self) -> bool:
        return self.replica.has_rounds and self.replica.is_member

    def clock(self) -> float:
        return self.driver._clock()

    # --- What the node learns --------------------------------------------------------------

    def learn(self, signed: SignedTransfer) -> None:
        """A version with its sender's signature: it can be proposed and reported."""
        if is_authorized_transfer(signed):
            event_id = signed.transfer.event_id()
            self.signed.setdefault(event_id, signed)
            self.events.setdefault(event_id, signed.transfer)

    def _event(self, event_id: str) -> Transfer | None:
        return self.events.get(event_id)

    def voted_round_0(self, event: Transfer) -> None:
        """This node voted in round 0 for a key: its rounds start, and the clock with them."""
        self.events.setdefault(event.event_id(), event)
        self.started.setdefault((event.sender, event.nonce), self.clock())

    # --- From states to messages -------------------------------------------------------------

    def _step(self, sender: str, nonce: int, entry: dict, certificate=None) -> list[dict]:
        if not self.enabled:
            return []

        result = self.replica.round_step(sender, nonce, entry, certificate)
        if result is None:
            return []

        before, after = result
        return self._messages(sender, nonce, before, after)

    def _messages(self, sender: str, nonce: int, before: dict | None, after: dict) -> list[dict]:
        key = (sender, nonce)
        old = before or {"round": 0, "prevotes": [], "precommits": [], "reports": [], "decided": None}
        out: list[dict] = []
        epoch = self.committee.epoch

        if after["decided"] is not None:
            self.started.pop(key, None)
        elif after["round"] != old["round"]:
            self.started[key] = self.clock()

        for round_, value in after["prevotes"]:
            if round_ >= 1 and [round_, value] not in old["prevotes"]:
                vote, event = self._sign(value, PREVOTE, round_)
                if vote is not None:
                    out.append(self._round_vote_message(event, vote, PREVOTE, round_, epoch))
                    out.extend(self._count(event, vote, PREVOTE, round_))

        for round_, value in after["precommits"]:
            if [round_, value] not in old["precommits"]:
                vote, event = self._sign(value, PRECOMMIT, round_)
                if vote is not None:
                    out.append(self._round_vote_message(event, vote, PRECOMMIT, round_, epoch))
                    out.extend(self._count(event, vote, PRECOMMIT, round_))

        new_reports = [entry for entry in after["reports"] if entry not in old["reports"]]
        # Only the report of the round the node is now in: the others were passed on the way.
        if new_reports:
            round_, report = max(new_reports, key=lambda entry: entry[0])
            signed = self._sign_report(sender, nonce, round_, report, after)
            if signed is not None:
                out.append(encode_new_round(signed, epoch))
                out.extend(self._take_report(signed))

        return out

    def _sign(self, value: str, phase: str, round_: int) -> tuple[Vote | None, Transfer | None]:
        """
        A prevote or precommit the model allowed. The version with its sender's signature is written
        first: the report of this member for the closure must hold what it voted for in any round
        (`voted_in_closure`), and without that proof it signs nothing.
        """
        signed = self.signed.get(value)
        if signed is None:
            LOG.warning("no signed version to vote for in a round", extra={"value": value, "phase": phase})
            return None, None
        self.replica.record_round_evidence(signed)
        return self.replica.sign_phase(signed.transfer, phase, round_), signed.transfer

    def _round_vote_message(self, event: Transfer, vote: Vote, phase: str, round_: int, epoch: int) -> dict:
        message = encode_round_vote(event, vote, phase, round_, epoch)
        signed = self.signed.get(event.event_id())
        if signed is not None:
            message["public_key"] = signed.public_key.hex()
            message["sender_signature"] = signed.signature.hex()
        return message

    def _sign_report(self, sender: str, nonce: int, round_: int, report: dict, state: dict) -> RoundReport | None:
        vote0 = None
        if report["vote0"] is not None:
            vote0 = self.signed.get(report["vote0"]) or self.replica.own_vote0(sender, nonce)
            if vote0 is None or vote0.transfer.event_id() != report["vote0"]:
                # The vote is on disk with its proof; without it the report would say less than it must.
                LOG.error("vote of round 0 without its proof", extra={"sender": sender, "nonce": nonce})
                return None

        best = None
        best_value = None
        if report["best"] is not None:
            best = self.replica.best_certificate(state)
            if best is None or best.round != report["best"]["round"] or best.event.event_id() != report["best"]["value"]:
                LOG.error("prepare certificate missing for a report", extra={"sender": sender, "nonce": nonce})
                return None
            best_value = self.signed.get(best.event.event_id())

        return self.replica.sign_report(sender, nonce, round_, vote0, best, best_value)

    # --- Votes of later rounds and precommits --------------------------------------------------

    def handle_round_vote(self, event: Transfer, vote: Vote, phase: str, round_: int, signed=None) -> list[dict]:
        if signed is not None:
            self.learn(signed)
        if not vote.verify(self.committee, event, phase, round_):
            self.driver._cost += self.driver.BAD_SIGNATURE_COST
            return []
        self.events.setdefault(event.event_id(), event)
        return self._count(event, vote, phase, round_)

    def _count(self, event: Transfer, vote: Vote, phase: str, round_: int) -> list[dict]:
        key = (event.sender, event.nonce, phase, round_, event.canonical())
        votes = self.votes.setdefault(key, {})
        votes[vote.validator] = vote

        if len(votes) < self.committee.quorum:
            return []

        certificate = QuorumCertificate(
            event,
            tuple(votes[validator] for validator in sorted(votes)),
            self.committee.epoch,
            phase,
            round_,
        )

        if phase == PREVOTE:
            if (event.sender, event.nonce, round_) in self.driver._prepares:
                return []
            signed = self.signed.get(event.event_id())
            return [encode_certificate(certificate, signed), *self.driver._take_prepare(certificate)]

        # A decision: the driver executes it, as any certificate that decides.
        if (event.sender, event.nonce, "decided") in self.prepared:
            return []
        self.prepared.add((event.sender, event.nonce, "decided"))
        return [encode_certificate(certificate), *self.driver._take_decision(certificate)]

    def prepare(self, certificate: QuorumCertificate) -> list[dict]:
        """A valid prepare certificate: `prepared`, and the precommit it allows."""
        event = certificate.event
        self.prepared.add((event.sender, event.nonce, certificate.round))
        self.events.setdefault(event.event_id(), event)
        return self._step(
            event.sender,
            event.nonce,
            {
                "kind": "prepared",
                "round": certificate.round,
                "value": event.event_id(),
                "signers": [vote.validator for vote in certificate.votes],
            },
            certificate,
        )

    def decided(self, certificate: QuorumCertificate) -> list[dict]:
        """A valid decision: `fast` or `committed`. Nothing to send: the state only stops the clock."""
        event = certificate.event
        signers = [vote.validator for vote in certificate.votes]
        if certificate.phase == VOTE:
            entry = {"kind": "fast", "value": event.event_id(), "signers": signers}
        else:
            entry = {"kind": "committed", "round": certificate.round, "value": event.event_id(), "signers": signers}
        self.started.pop((event.sender, event.nonce), None)
        return self._step(event.sender, event.nonce, entry)

    # --- Reports and proposals ---------------------------------------------------------------

    def leader(self, sender: str, nonce: int, round_: int) -> int:
        return lean_core.leader(self.committee.n, round_offset(sender, nonce), round_)

    def handle_new_round(self, report: RoundReport) -> list[dict]:
        if not self.enabled:
            return []
        if not report.verify(self.committee):
            self.driver._cost += self.driver.BAD_SIGNATURE_COST
            return []
        return self._take_report(report)

    def _take_report(self, report: RoundReport) -> list[dict]:
        if report.vote0 is not None:
            self.learn(report.vote0)
        if report.best_value is not None:
            self.learn(report.best_value)
        if report.best is not None:
            self.events.setdefault(report.best.event.event_id(), report.best.event)

        key = (report.sender, report.nonce)
        reports = self.reports.setdefault((*key, report.round), {})
        reports[report.validator] = report
        out: list[dict] = []

        # `f+1` members in a later round: at least one honest timed out, so this node goes too. A key
        # it never heard of it joins at the first report with a version: otherwise a key only one
        # member voted on could find no quorum of reports, and its closure would wait for ever.
        state = self.replica.round_state(*key)
        own = 0 if state is None else state["round"]
        joins = len(reports) >= self.committee.f + 1 or (state is None and report.vote0 is not None)
        if report.round > own and joins and (state is None or state["decided"] is None):
            out.extend(self._jump(*key, report.round))

        out.extend(self._propose_if_leader(*key, report.round))
        return out

    def _jump(self, sender: str, nonce: int, round_: int) -> list[dict]:
        """Timeouts up to `round_`, which `Rounds.step` allows at any time. Only the last report goes."""
        out: list[dict] = []
        before = self.replica.round_state(sender, nonce)
        state = before
        while (0 if state is None else state["round"]) < round_:
            result = self.replica.round_step(sender, nonce, {"kind": "timeout"})
            if result is None:
                return out
            state = result[1]
        if state is not before:
            out.extend(self._messages(sender, nonce, before, state))
        return out

    def _propose_if_leader(self, sender: str, nonce: int, round_: int) -> list[dict]:
        if (sender, nonce, round_) in self.proposed:
            return []
        if self.committee.index_of(self.replica._identity.public_key) != self.leader(sender, nonce, round_):
            return []

        reports = self.reports.get((sender, nonce, round_), {})
        if len(reports) < self.committee.quorum:
            return []

        chosen = tuple(reports[member] for member in sorted(reports))
        forced = lean_core.choose(self.committee.n, self.committee.f, [self._entry(r) for r in chosen])

        if forced is not None:
            value = self.signed.get(forced)
        else:
            value = self.replica.own_vote0(sender, nonce) or next(
                (
                    signed
                    for signed in self.signed.values()
                    if (signed.transfer.sender, signed.transfer.nonce) == (sender, nonce)
                ),
                None,
            )

        if value is None:
            LOG.warning("leader has no signed version to propose", extra={"sender": sender, "nonce": nonce})
            return []

        proposal = self.replica.sign_proposal(round_, value, chosen)
        if proposal is None:
            return []

        self.proposed.add((sender, nonce, round_))
        message = encode_proposal(proposal, self.committee.epoch)
        return [message, *self.handle_proposal(proposal)]

    @staticmethod
    def _entry(report: RoundReport) -> dict:
        return {
            "member": report.validator,
            "vote0": None if report.vote0 is None else report.vote0.transfer.event_id(),
            "best": None
            if report.best is None
            else {
                "round": report.best.round,
                "value": report.best.event.event_id(),
                "signers": [vote.validator for vote in report.best.votes],
            },
        }

    def handle_proposal(self, proposal: RoundProposal) -> list[dict]:
        if not self.enabled:
            return []

        sender, nonce = proposal.key
        if not proposal.verify_leader(self.committee, self.leader(sender, nonce, proposal.round)):
            self.driver._cost += self.driver.BAD_SIGNATURE_COST
            return []

        reports = [
            report
            for report in proposal.reports
            if (report.sender, report.nonce, report.round) == (sender, nonce, proposal.round)
            and report.verify(self.committee)
        ]
        self.learn(proposal.value)

        out = []
        state = self.replica.round_state(sender, nonce)
        if state is not None and state["decided"] is not None:
            return out
        if (0 if state is None else state["round"]) < proposal.round:
            out.extend(self._jump(sender, nonce, proposal.round))

        out.extend(
            self._step(
                sender,
                nonce,
                {
                    "kind": "proposal",
                    "round": proposal.round,
                    "value": proposal.value.transfer.event_id(),
                    "reports": [self._entry(report) for report in reports],
                },
            )
        )
        return out

    # --- Time ----------------------------------------------------------------------------------

    def timeout_of(self, round_: int) -> float:
        return min(self.ROUND_FIRST_SECONDS * 2**round_, self.ROUND_LONGEST_SECONDS)

    def hurry(self) -> list[dict]:
        """An order to close the epoch: every open key this node voted on moves to the next round now."""
        if not self.enabled:
            return []
        out: list[dict] = []
        for sender, nonce, state in self.replica.round_states():
            if state["decided"] is None and state["round"] == 0 and state["prevotes"]:
                out.extend(self._step(sender, nonce, {"kind": "timeout"}))
        return out

    def tick(self) -> list[dict]:
        """Keys that waited too long in their round move to the next one, and report."""
        if not self.enabled:
            return []

        now = self.clock()
        out: list[dict] = []

        for key, since in list(self.started.items()):
            state = self.replica.round_state(*key)
            if state is None or state["decided"] is not None:
                self.started.pop(key, None)
                continue
            if now - since >= self.timeout_of(state["round"]):
                out.extend(self._step(*key, {"kind": "timeout"}))

        return out
