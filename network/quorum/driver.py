"""
Messages in and out: what a node answers, asks and sends again. It calls the replica, never the network.

Quorum mode: docs/FORMAL-SPECIFICATION.md, section 13.1. The model is in formal/lean/PSystem/Quorum.lean.
"""

import heapq
import json
import time
from bisect import bisect_left
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import (
    dataclass,
    replace,
)

from core.attestation import (
    Committee,
    EpochChange,
    EpochClosure,
    EpochReport,
    Governance,
    QuorumCertificate,
    Snapshot,
    SnapshotAttestation,
    Vote,
    is_authorized_transfer,
)
from core.equivocation import EquivocationProof
from core.event import Transfer
from core.signed_event import SignedTransfer
from network.message import (
    decode_new_round,
    decode_proposal,
    decode_round_vote,
    certificate_sync_request_epoch,
    decode_certificate,
    decode_certificate_and_signed,
    decode_certificate_sync,
    decode_certificate_sync_request,
    decode_epoch_change,
    decode_epoch_closure,
    decode_epoch_report,
    decode_snapshot,
    decode_snapshot_request,
    decode_snapshot_vote,
    decode_vote,
    decode_vote_request,
    encode_certificate,
    encode_certificate_sync,
    encode_certificate_sync_request,
    encode_epoch_change,
    encode_epoch_closure,
    encode_epoch_report,
    encode_snapshot,
    encode_snapshot_request,
    encode_snapshot_vote,
    encode_vote,
    encode_vote_request,
)
from network.quorum.common import (
    LOG,
    VoteStoreError,
    is_executable_event,
)
from network.quorum.replica import QuorumReplica
from network.quorum.rounds import RoundDriver


QUORUM_MESSAGE_TYPES = frozenset(
    {
        "VOTE_REQUEST",
        "VOTE",
        "CERTIFICATE",
        "CERTIFICATE_SYNC",
        "CERTIFICATE_SYNC_REQUEST",
        "EPOCH_CHANGE",
        "EPOCH_REPORT",
        "EPOCH_CLOSURE",
        "SNAPSHOT_REQUEST",
        "SNAPSHOT_VOTE",
        "SNAPSHOT",
        "ROUND_VOTE",
        "NEW_ROUND",
        "PROPOSAL",
    }
)

# Well under the 16 MiB of a frame. A node that needs more asks again.
SYNC_BATCH_BYTES = 4 * 1024 * 1024
# What a bad signature costs a peer, in tokens of its 5000 per second: 50 of them per second, which
# take under 1% of a core. An honest peer sends none, and it only slows the one that does.
BAD_SIGNATURE_COST = 100
# A request for a snapshot makes a member derive a state from its log. A peer pays one token for this many
# steps of that derivation, and a bad signature's worth if the digest is not what the member derives. An
# attestation already given is given again from memory, for the last few requests. Values chosen by judgement.
SNAPSHOT_STEPS_PER_TOKEN = 20
SNAPSHOT_ANSWERS_KEPT = 16
# Certificates that cannot run yet. A certificate that can run never counts against this. One left
# out does not enter `_known`, so it comes back with synchronization.
MAX_BUFFERED_CERTIFICATES = 100_000
# Events being collected votes for, started here: only who holds the token of the API starts them.
MAX_AGGREGATING_EVENTS = 100_000
# A sender left out is one the node asks everything about, which costs traffic and is
# still correct. The limit keeps the request itself within a frame.
SYNC_MAX_FRONTIER_SENDERS = 100_000


@dataclass(frozen=True)
class DriverOutput:
    """What to send. Sending comes after the call, with no lock held."""

    replies: tuple[dict, ...] = ()
    broadcasts: tuple[dict, ...] = ()
    # What the message cost the node beyond reading it, in tokens of the peer that sent it.
    cost: int = 0


_NOTHING = DriverOutput()


@dataclass
class _Resend:
    """An event this node asks votes for, and when to ask again."""

    signed: SignedTransfer
    due: float
    wait: float
    started: float
    # After a restart: its own vote is on disk, and it signs it again when the event gets its turn.
    needs_own_vote: bool = False


class QuorumDriver:
    BAD_SIGNATURE_COST = BAD_SIGNATURE_COST
    # How long a closure in progress waits before what it needs is sent again.
    EPOCH_RETRY_SECONDS = 10.0
    # How long a snapshot is asked for before starting another: members behind catch up meanwhile.
    SNAPSHOT_ASK_SECONDS = 60.0
    # An event with no certificate is asked for again after this long, then twice as long each time
    # up to the second number, because it may never get one. At most this many requests in a round,
    # so a node that is behind on many events pays for it slowly. Values chosen by judgement.
    RESEND_FIRST_SECONDS = 2.0
    RESEND_LONGEST_SECONDS = 30.0
    RESEND_MOST_IN_A_ROUND = 256
    COLLECTION_TIMEOUT_SECONDS = 300.0

    """
    The protocol around a replica: takes messages, returns messages to send. It
    uses no network and no Node.

    What it decides that the model has no counterpart for: which vote requests
    reach the replica, which votes count, and when the node halts. The retries of
    the buffer are what the model gets by delivering an input again.

    Each node aggregates only the votes for events submitted to it. If that node
    is lost, nobody completes the certificate until someone submits the event
    elsewhere. The votes it gathered are in memory and lost at a restart, and it asks for them
    again: a new vote gives the same signature. The events it took are on disk with its own vote.

    It asks again for what has no certificate, since a message can be lost with its connection and
    the synchronization carries only certificates. A validator can answer as
    often as it is asked: `voteAllowed` admits the event it already voted for and no other, and
    `no_double_spend` holds for any list of inputs, so a repeated request is one more input. This
    makes a certificate more likely. It promises none: see `honest_sender_certifies`.

    The buffer has a limit, and that does not make the result depend on the order of arrival: a
    certificate left out comes back with synchronization, and one that can run is never left out.
    It is in memory, so a certificate still waiting is lost at a restart and has to be delivered
    again.

    Synchronization adds no transition: a certificate that arrives in a batch goes
    through the same path as one that arrives alone, and the model already allows any
    list of inputs for each node. A node asks with the next nonce of each sender. The
    position in the log would not do, because it differs from node to node. Nonces do,
    because a sender's nonces execute in sequence.

    Not thread-safe: the caller serializes the calls. A VoteStoreError propagates,
    and then nothing is to be sent.
    """

    def __init__(
        self,
        replica: QuorumReplica,
        governance: Governance | None = None,
        max_nonce_ahead: int | None = None,
        require_funds: bool = False,
        max_evidence: int | None = None,
        clock: Callable[[], float] = time.monotonic,
        snapshot_every: int | None = None,
        prune: bool = False,
    ) -> None:
        self.replica = replica
        self.governance = governance
        self._clock = clock
        self._epoch_activity = clock()
        # Limits against who fills a node with events of their own. Refusing a vote cannot
        # break safety: `no_double_spend` holds for any list of inputs, and a refused request
        # is one input less. It can delay an honest sender, who sends the event again. So what
        # these depend on is the state of this node, and that is allowed for a vote: the
        # first vote already depends on what a node received first.
        self.max_nonce_ahead = max_nonce_ahead
        self.require_funds = require_funds
        self.max_evidence = max_evidence
        # Events between snapshots, None for no snapshots. Pruning is off unless asked for: it
        # takes away the history, and with it the certificate of an old event.
        self.snapshot_every = snapshot_every
        self.prune = prune
        self._snapshot: Snapshot | None = None
        self._snapshot_votes: dict[int, SnapshotAttestation] = {}
        # Attestations this member gave, by request: see `_handle_snapshot_request`.
        self._snapshot_answers: OrderedDict = OrderedDict()
        self._snapshot_started = 0.0
        # The order this node is collecting reports for.
        self._change: EpochChange | None = None
        self._reports: dict[int, EpochReport] = {}
        self.equivocations: dict[tuple[str, int], EquivocationProof] = {}
        self.signed_events: dict[str, SignedTransfer] = {}
        self._first_signed: dict[tuple[str, int], SignedTransfer] = {}
        self._aggregating: dict[bytes, tuple[Transfer, dict[int, Vote]]] = {}
        self._to_resend: dict[bytes, _Resend] = {}
        self._buffer: dict[str, QuorumCertificate] = {}
        # The same, by sender and nonce: only the next nonce of a sender can run.
        self._waiting: dict[str, dict[int, str]] = {}
        self.max_buffered = MAX_BUFFERED_CERTIFICATES
        self.certificates_left_out = 0
        self.max_aggregating = MAX_AGGREGATING_EVENTS
        self._cost = 0
        self._unpublished_signed: list[SignedTransfer] = []
        self._unpublished_proofs: list[EquivocationProof] = []
        # One certificate for each (sender, nonce), executed or waiting: a second
        # one for another event is the conflict that halts the node.
        self._known: dict[tuple[str, int], QuorumCertificate] = {
            (certificate.event.sender, certificate.event.nonce): certificate
            for certificate in replica.log
        }
        # The log by sender, in order of nonce, so that an answer does not read it all.
        self._log_by_sender: dict[str, list[QuorumCertificate]] = {}
        self._indexed = 0
        self.requests_resent = 0
        # Prepare certificates seen, by key and round: two for different events in one round are a
        # proof that more than f members are faulty (`prepared_same_round`).
        self._prepares: dict[tuple[str, int, int], QuorumCertificate] = {}
        self.rounds = RoundDriver(self)
        # An order to close this epoch, waiting a little for the keys this node voted on to be decided,
        # and meanwhile no new vote of round 0. The wait is bounded: a member that waited for good could
        # keep the closure from forming, and with it every vote. What is still undecided goes in the
        # report with what was voted for in every round, so that nothing decided is lost
        # (`voted_in_closure`); such a key stays locked in the next epoch.
        self._closing: EpochChange | None = None
        self._closing_since = 0.0

        if not self.halted:
            self._resume_gathering()
            # Decisions this node held without executing them: a restart keeps them.
            for certificate in self.replica.decided_held():
                if self.replica.certificate_was_valid(certificate):
                    self._accept(certificate)

    def _resume_gathering(self) -> None:
        # Its own vote comes when an event gets its turn: a signer in another process could
        # hold up the start of the node, and there may be many.
        for signed in self.replica.gathering()[: self.max_aggregating]:
            canonical = signed.transfer.canonical()
            self._aggregating[canonical] = (signed.transfer, {})
            self._to_resend[canonical] = _Resend(
                signed,
                self._clock(),
                self.RESEND_FIRST_SECONDS,
                self._clock(),
                needs_own_vote=True,
            )

    @property
    def gathering_count(self) -> int:
        return len(self._aggregating)

    @property
    def gathering_oldest_seconds(self) -> float:
        """Since this process started asking, so a restart starts it again. 0 with nothing."""
        oldest = next(iter(self._to_resend.values()), None)
        return 0.0 if oldest is None else self._clock() - oldest.started

    @property
    def committee(self) -> Committee:
        return self.replica.committee

    @property
    def halted(self) -> bool:
        return self.replica.halted()

    def handle_message(self, message: dict) -> DriverOutput:
        """
        Raises ValueError if the message is malformed, and the caller closes the
        connection. A message of the right form that is not valid only gets no
        answer: anyone can send one, and it must never stop the node.
        """
        self._cost = 0
        output = self._dispatch(message)

        if self._cost:
            return replace(output, cost=self._cost)

        return output

    def _dispatch(self, message: dict) -> DriverOutput:
        message_type = message.get("type")

        if message_type == "VOTE_REQUEST":
            return self._handle_vote_request(decode_vote_request(message))

        if message_type == "VOTE":
            return self._handle_vote(*decode_vote(message))

        if message_type == "CERTIFICATE":
            certificate, signed = decode_certificate_and_signed(message)
            if signed is not None:
                self.rounds.learn(signed)
            return self._handle_certificate(certificate)

        if message_type == "CERTIFICATE_SYNC":
            return self._handle_certificate_sync(decode_certificate_sync(message))

        if message_type == "CERTIFICATE_SYNC_REQUEST":
            return self._handle_sync_request(
                decode_certificate_sync_request(message),
                certificate_sync_request_epoch(message),
            )

        if message_type == "EPOCH_CHANGE":
            return self._handle_epoch_change(decode_epoch_change(message))

        if message_type == "EPOCH_REPORT":
            return self._handle_epoch_report(*decode_epoch_report(message))

        if message_type == "EPOCH_CLOSURE":
            return self._handle_epoch_closure(decode_epoch_closure(message))

        if message_type == "SNAPSHOT_REQUEST":
            return self._handle_snapshot_request(*decode_snapshot_request(message))

        if message_type == "SNAPSHOT_VOTE":
            return self._handle_snapshot_vote(*decode_snapshot_vote(message))

        if message_type == "SNAPSHOT":
            return self._handle_snapshot(decode_snapshot(message))

        if message_type == "ROUND_VOTE":
            event, vote, phase, round_, epoch, signed = decode_round_vote(message)
            if self.halted or epoch != self.committee.epoch:
                return _NOTHING
            return DriverOutput(broadcasts=tuple(self.rounds.handle_round_vote(event, vote, phase, round_, signed)))

        if message_type == "NEW_ROUND":
            report, epoch = decode_new_round(message)
            if self.halted or epoch != self.committee.epoch:
                return _NOTHING
            # A member still in rounds for a key this node has a decision for: the decision is the answer.
            known = self._known.get((report.sender, report.nonce))
            if known is not None and known.decides(self.replica.committee_of(known)):
                return DriverOutput(replies=(encode_certificate(known),))
            return DriverOutput(broadcasts=tuple(self.rounds.handle_new_round(report)))

        if message_type == "PROPOSAL":
            proposal, epoch = decode_proposal(message)
            if self.halted or epoch != self.committee.epoch:
                return _NOTHING
            return DriverOutput(broadcasts=tuple(self.rounds.handle_proposal(proposal)))

        raise ValueError("NOT A QUORUM MESSAGE")

    def sync_request(self) -> dict | None:
        """What to ask a peer for. None once halted: there is nothing more to do."""
        if self.halted:
            return None

        return encode_certificate_sync_request(self._frontier(), self.committee.epoch)

    def _frontier(self) -> dict[str, int]:
        self._refresh_log_index()
        state = self.replica.state
        frontier = {sender: state.nonce(sender) for sender in self._log_by_sender}

        # Otherwise a peer that pruned would take this node for one behind its snapshot, every time.
        if self.replica.base is not None:
            frontier.update(
                (sender, state.nonce(sender)) for sender in self.replica.base.state.nonces
            )

        # What waits in the buffer counts as known. Otherwise a batch that cannot run
        # yet would come back unchanged, and asking again would never reach the rest.
        for sender in {certificate.event.sender for certificate in self._buffer.values()}:
            nonce = frontier.get(sender, state.nonce(sender))

            while (sender, nonce) in self._known:
                nonce += 1

            frontier[sender] = nonce

        return dict(sorted(frontier.items())[:SYNC_MAX_FRONTIER_SENDERS])

    def _refresh_log_index(self) -> None:
        log = self.replica.log

        for certificate in log[self._indexed:]:
            self._log_by_sender.setdefault(
                certificate.event.sender,
                [],
            ).append(certificate)

        self._indexed = len(log)

    def _handle_sync_request(self, frontier: dict[str, int], epoch: int = 0) -> DriverOutput:
        # Also after a halt: what was executed before it is still certified. The closures
        # come first, because a certificate of a later epoch needs them to verify.
        closures = tuple(
            encode_epoch_closure(closure)
            for closure in self.replica.closures(epoch)
        )
        self._refresh_log_index()
        snapshot = self._snapshot_for(frontier)
        batch = []
        size = 0

        for sender in sorted(self._log_by_sender):
            certificates = self._log_by_sender[sender]
            # By nonce and not by position: after a snapshot the log of a sender can have holes.
            start = bisect_left(
                certificates,
                frontier.get(sender, 0),
                key=lambda certificate: certificate.event.nonce,
            )

            for certificate in certificates[start:]:
                size += len(json.dumps(encode_certificate(certificate)))

                if batch and size > SYNC_BATCH_BYTES:
                    return DriverOutput(
                        replies=(*closures, *snapshot, encode_certificate_sync(batch)),
                    )

                batch.append(certificate)

        if not batch:
            return DriverOutput(replies=(*closures, *snapshot))

        return DriverOutput(replies=(*closures, *snapshot, encode_certificate_sync(batch)))

    def _snapshot_for(self, frontier: dict[str, int]) -> tuple[dict, ...]:
        """The snapshot, if this peer needs what this node holds only inside it."""
        base = self.replica.base

        # One signed before version 2 is good for this node only: a peer would refuse it.
        if base is None or base.is_legacy:
            return ()

        initial = self.replica._initial_state

        for sender, floor in base.state.nonces.items():
            needed = max(frontier.get(sender, 0), initial.nonce(sender))

            if needed < floor:
                held = self._log_by_sender.get(sender, [])
                nonce_of = lambda certificate: certificate.event.nonce
                count = bisect_left(held, floor, key=nonce_of) - bisect_left(
                    held, needed, key=nonce_of
                )

                # Not only the start: a snapshot can leave holes anywhere in this log.
                if count != floor - needed:
                    return (encode_snapshot(base),)

        return ()

    def _handle_certificate_sync(
        self,
        certificates: list[QuorumCertificate],
    ) -> DriverOutput:
        learned = False

        for certificate in certificates:
            if self.halted:
                return _NOTHING

            event = certificate.event
            known = self._known.get((event.sender, event.nonce))

            # No signature to check, so that sending the log again costs nothing.
            if known is not None and known.event.canonical() == event.canonical():
                continue

            if self.replica.is_covered(event) and self.replica.has_executed_id(event.event_id()):
                continue

            # No honest node sends this. Stopping here means that a frame full of bad
            # certificates costs one check of a signature.
            if not self.replica.certificate_is_valid(certificate):
                self._cost += BAD_SIGNATURE_COST
                return _NOTHING

            # One left out teaches nothing. Asking again for it would never end.
            if self._accept(certificate):
                learned = True

        request = self.sync_request() if learned else None

        # Only after learning something: this is what ends the exchange, and a peer
        # cannot make it last without new certificates.
        if request is None:
            return _NOTHING

        return DriverOutput(replies=(request,))

    def propose_epoch_change(self, change: EpochChange) -> DriverOutput:
        """
        Order the end of this epoch, as a proposer. This node collects the reports. Others can do the
        same at the same time, and it costs only messages: any quorum of reports is a closure, and
        `one_order_never_blocks` says no proposer can stand in the way of another.
        """
        if (
            self.governance is None
            or self.halted
            or not change.verify(self.governance, self.committee)
        ):
            return _NOTHING

        self._change = change
        self._reports = {}
        self._epoch_activity = self._clock()
        report = self._report(change)

        if report is not None:
            self._reports[report.validator] = report

        closed = self._closure_if_reported()
        return DriverOutput(broadcasts=(encode_epoch_change(change), *closed.broadcasts))

    def retry(self) -> DriverOutput:
        """Call it now and then: what is in progress goes on."""
        epoch = self._retry_epoch()
        snapshot = self._snapshot_tick()
        rounds = () if self.halted else tuple(self.rounds.tick())

        rounds += tuple(getattr(self, "_pending_reports", ()))
        self._pending_reports = ()

        # A closure that waited for decisions: the report goes to every member, since whoever
        # collects it may be any of them.
        if self._closing is not None and not self.halted:
            change = self._closing
            report = self._report(change)
            if report is not None:
                rounds += (encode_epoch_report(change.change_id, report),)
        return DriverOutput(
            broadcasts=(*epoch.broadcasts, *snapshot.broadcasts, *self._resend_requests(), *rounds),
        )

    def resend_soon(self) -> None:
        """A new connection: what was lost on the old one need not wait for its turn."""
        for pending in self._to_resend.values():
            pending.due = self._clock()
            pending.wait = self.RESEND_FIRST_SECONDS

    def _resend_requests(self) -> list[dict]:
        # A halt empties the aggregation, so nothing is asked for after one.
        now = self._clock()
        state = self.replica.state
        forgotten = []

        for canonical, pending in list(self._to_resend.items()):
            event = pending.signed.transfer
            known = self._known.get((event.sender, event.nonce))

            # An event certified by another route, or another version certified, or a closure that
            # took away the votes: no request can help any more.
            if (
                canonical not in self._aggregating
                or known is not None
                or state.nonce(event.sender) > event.nonce
            ):
                del self._to_resend[canonical]
                self._aggregating.pop(canonical, None)

                # Its own certificate may be waiting for an earlier nonce, in memory. The row stays
                # until it runs, since a restart would lose that certificate.
                if known is None or known.event.canonical() != canonical:
                    forgotten.append(event.event_id())
                continue

            if now - pending.started >= self.COLLECTION_TIMEOUT_SECONDS:
                votes_count = 0
                aggregating = self._aggregating.get(canonical)
                if aggregating is not None:
                    votes_count = len(aggregating[1])
                LOG.warning(
                    "certificate_collection_timeout",
                    extra={
                        "sender": event.sender,
                        "nonce": event.nonce,
                        "event_id": event.event_id(),
                        "epoch": self.committee.epoch,
                        "age_seconds": now - pending.started,
                        "votes": votes_count,
                    },
                )
                del self._to_resend[canonical]
                self._aggregating.pop(canonical, None)
                forgotten.append(event.event_id())
                continue

            if forgotten:
                try:
                    self.replica.forget_gathering(forgotten)
                except VoteStoreError as error:
                    # A row too many only asks again, after a restart, and is forgotten then.
                    LOG.error("cannot forget what was gathering", extra={"reason": str(error)})
                forgotten = []

        if forgotten:
            try:
                self.replica.forget_gathering(forgotten)
            except VoteStoreError as error:
                LOG.error("cannot forget what was gathering", extra={"reason": str(error)})

        # The one waiting longest first, so that events that will never get a quorum, however many,
        # do not take the turn of the others: once asked, they go to the back.
        due = heapq.nsmallest(
            self.RESEND_MOST_IN_A_ROUND,
            (pending for pending in self._to_resend.values() if pending.due <= now),
            key=lambda pending: (pending.due, pending.signed.transfer.nonce),
        )

        messages = []

        for pending in due:
            pending.wait = min(2 * pending.wait, self.RESEND_LONGEST_SECONDS)
            pending.due = now + pending.wait
            own = self._own_vote_after_a_restart(pending)
            messages.extend(own or [encode_vote_request(pending.signed)])

        self.requests_resent += len(messages)
        return messages

    def _own_vote_after_a_restart(self, pending: _Resend) -> list[dict]:
        """
        Through the same check as any vote. A store restored from a backup refuses, and stays as it
        was: it signs nothing, it gathers the votes of the others, and that needs one more of them.
        """
        if not pending.needs_own_vote:
            return []

        event = pending.signed.transfer
        vote = self.replica.handle_vote_request(event, pending.signed)

        if vote is None:
            return []

        self.rounds.learn(pending.signed)
        self.rounds.voted_round_0(event)
        pending.needs_own_vote = False
        _, votes = self._aggregating[event.canonical()]
        votes[vote.validator] = vote
        return self._complete(event, votes)

    def _retry_epoch(self) -> DriverOutput:
        """
        Whoever reported and sees no closure asks for the reports itself, since whoever proposed may
        be dead. Several nodes doing this cost messages and nothing else.
        """
        if (
            self.governance is None
            or self.halted
            or self._clock() - self._epoch_activity < self.EPOCH_RETRY_SECONDS
        ):
            return _NOTHING

        if self._change is None:
            reported = self.replica.reported_change()

            if reported is None or not reported.verify(self.governance, self.committee):
                return _NOTHING

            self._change = reported
            report = self._report(reported)

            if report is not None:
                self._reports[report.validator] = report

        self._epoch_activity = self._clock()
        closed = self._closure_if_reported()
        return DriverOutput(broadcasts=(encode_epoch_change(self._change), *closed.broadcasts))

    def _snapshot_is_due(self) -> bool:
        replica = self.replica
        index = self.committee.index_of(replica._identity.public_key)

        if index is None:
            return False

        # A snapshot by another member does as well, so members start at different points and most
        # of the time only one asks.
        if replica.executed_since_base() >= self.snapshot_every * (1 + index / self.committee.n):
            return True

        # A snapshot of an ended committee, or signed before version 2, is good for this node and for
        # no other.
        return (
            self.prune
            and replica.base is not None
            and (replica.base.epoch != self.committee.epoch or replica.base.is_legacy)
        )

    def _snapshot_tick(self) -> DriverOutput:
        if self.snapshot_every is None or self.halted:
            return _NOTHING

        if (
            self._snapshot is not None
            and self._clock() - self._snapshot_started < self.SNAPSHOT_ASK_SECONDS
        ):
            return DriverOutput(broadcasts=(self._snapshot_request(),))

        self._snapshot = None

        if not self._snapshot_is_due():
            return _NOTHING

        return self.propose_snapshot()

    def _snapshot_request(self) -> dict:
        return encode_snapshot_request(
            self._snapshot.epoch,
            self._snapshot.digest,
            self._snapshot.state.nonces,
        )

    def propose_snapshot(self) -> DriverOutput:
        """Ask the committee to sign the state of this node. Two at once do no harm: both are true."""
        candidate = self.replica.candidate_snapshot()
        attestation = self.replica.attest_snapshot(
            candidate.epoch,
            candidate.digest,
            candidate.state.nonces,
        )

        if attestation is None:
            return _NOTHING

        self._snapshot = candidate
        self._snapshot_votes = {attestation.validator: attestation}
        self._snapshot_started = self._clock()
        return DriverOutput(broadcasts=(self._snapshot_request(),))

    def _handle_snapshot_request(
        self,
        epoch: int,
        digest: str,
        nonces: dict[str, int],
    ) -> DriverOutput:
        replica = self.replica

        if self.halted:
            return _NOTHING

        base = None if replica.base is None else (replica.base.epoch, replica.base.digest)
        key = (self.committee.committee_id, base, epoch, digest, tuple(sorted(nonces.items())))
        attestation = self._snapshot_answers.get(key)

        if attestation is not None:
            self._snapshot_answers.move_to_end(key)
        else:
            steps = replica.derive_steps
            attestation = replica.attest_snapshot(epoch, digest, nonces)
            work = replica.derive_steps - steps
            self._cost += work // SNAPSHOT_STEPS_PER_TOKEN

            if attestation is None:
                # Derived, and not this digest: what no honest proposer asks.
                if work:
                    self._cost += BAD_SIGNATURE_COST

                return _NOTHING

            self._snapshot_answers[key] = attestation

            while len(self._snapshot_answers) > SNAPSHOT_ANSWERS_KEPT:
                self._snapshot_answers.popitem(last=False)

        return DriverOutput(replies=(encode_snapshot_vote(digest, attestation),))

    def _handle_snapshot_vote(
        self,
        digest: str,
        attestation: SnapshotAttestation,
    ) -> DriverOutput:
        candidate = self._snapshot

        if (
            candidate is None
            or digest != candidate.digest
            or candidate.epoch != self.committee.epoch
        ):
            return _NOTHING

        if not attestation.verify(self.committee, digest):
            self._cost += BAD_SIGNATURE_COST
            return _NOTHING

        self._snapshot_votes[attestation.validator] = attestation

        if len(self._snapshot_votes) < self.committee.quorum:
            return _NOTHING

        snapshot = Snapshot(
            candidate.epoch,
            candidate.state,
            candidate.ids,
            tuple(self._snapshot_votes[v] for v in sorted(self._snapshot_votes)),
        )
        self._snapshot = None
        self._snapshot_votes = {}
        self._take_snapshot(snapshot)
        return DriverOutput(broadcasts=(encode_snapshot(snapshot),))

    def _handle_snapshot(self, snapshot: Snapshot) -> DriverOutput:
        if self.halted:
            return _NOTHING

        # Refused or nothing new: reading it was the cost, and it is the same.
        if not self._take_snapshot(snapshot):
            self._cost += BAD_SIGNATURE_COST
            return _NOTHING

        request = self.sync_request()
        return _NOTHING if request is None else DriverOutput(replies=(request,))

    def _take_snapshot(self, snapshot: Snapshot) -> bool:
        replica = self.replica

        if not replica.install_snapshot(snapshot):
            return False

        LOG.info(
            "snapshot taken",
            extra={"epoch": snapshot.epoch, "digest": snapshot.digest, "events": len(snapshot.ids)},
        )

        if self.prune:
            for certificate in replica.prune_covered():
                self._known.pop((certificate.event.sender, certificate.event.nonce), None)

        self._log_by_sender = {}
        self._indexed = 0

        # What was waiting and is now inside the snapshot will never run: it already did.
        for event_id, certificate in list(self._buffer.items()):
            if replica.is_covered(certificate.event):
                self._no_longer_waiting(event_id)

        self._retry_buffer()
        return True

    def _handle_epoch_change(self, change: EpochChange) -> DriverOutput:
        if (
            self.governance is None
            or self.halted
            or not change.verify(self.governance, self.committee)
        ):
            self._cost += BAD_SIGNATURE_COST
            return _NOTHING

        report = self._report(change)

        if report is None:
            return _NOTHING

        self._epoch_activity = self._clock()
        return DriverOutput(replies=(encode_epoch_report(change.change_id, report),))

    def _handle_epoch_report(self, change_id: str, report: EpochReport) -> DriverOutput:
        if (
            self._change is None
            or change_id != self._change.change_id
        ):
            return _NOTHING

        if not report.verify(self.committee, change_id):
            self._cost += BAD_SIGNATURE_COST
            return _NOTHING

        self._reports[report.validator] = report
        self._epoch_activity = self._clock()
        return self._closure_if_reported()

    def _closure_if_reported(self) -> DriverOutput:
        if len(self._reports) < self.committee.quorum:
            return _NOTHING

        closure = EpochClosure(
            self._change,
            tuple(self._reports[validator] for validator in sorted(self._reports)),
        )
        self._install(closure)
        return DriverOutput(broadcasts=(encode_epoch_closure(closure),))

    def _handle_epoch_closure(self, closure: EpochClosure) -> DriverOutput:
        """
        One that does not continue the epoch in force is ignored, with no judgement: a node
        behind gets the ones before it by synchronizing.
        """
        if (
            self.governance is None
            or self.halted
            or closure.change.previous_id != self.committee.committee_id
        ):
            return _NOTHING

        if not closure.verify(self.governance, self.committee):
            self._cost += BAD_SIGNATURE_COST
            return _NOTHING

        self._install(closure)
        return _NOTHING

    def _install(self, closure: EpochClosure) -> None:
        self.replica.install_closure(closure)
        LOG.warning(
            "new epoch installed",
            extra={
                "epoch": self.committee.epoch,
                "committee_id": self.committee.committee_id,
                "locks": len(closure.locks(self.replica.committee_before_last())),
            },
        )
        # Votes collected so far were signed for the committee that has ended.
        self._aggregating.clear()
        self._change = None
        # So were the rounds: a new committee starts its keys anew, under the locks of the closure.
        self._closing = None
        self._prepares.clear()
        self.rounds = RoundDriver(self)
        self._reports = {}
        self._epoch_activity = self._clock()
        self._snapshot = None
        self._snapshot_votes = {}

        if self.prune:
            self.replica.apply_floor()

        self._retry_buffer()

    def submit(self, signed: SignedTransfer) -> DriverOutput:
        """
        Start an event here: vote for it, then ask the others. If it already has a
        certificate, send that instead. If the vote is refused, nobody is asked,
        because an honest node does not ask for what it would not sign.
        """
        if self.halted or self._closing is not None or not self._is_admitted(signed.transfer):
            return _NOTHING

        if not self._is_authorized(signed):
            return _NOTHING

        self._record_signed(signed)
        event = signed.transfer
        known = self._known.get((event.sender, event.nonce))

        if known is not None and known.event.canonical() == event.canonical():
            return DriverOutput(broadcasts=(encode_certificate(known),))

        if (
            event.canonical() not in self._aggregating
            and len(self._aggregating) >= self.max_aggregating
        ):
            return _NOTHING

        vote = self.replica.handle_vote_request(event, signed, gathering=True)

        if vote is None:
            return _NOTHING

        self.rounds.learn(signed)
        self.rounds.voted_round_0(event)
        _, votes = self._aggregating.setdefault(event.canonical(), (event, {}))
        votes[vote.validator] = vote
        complete = self._complete(event, votes)

        if complete:
            return DriverOutput(broadcasts=tuple(complete))

        self._to_resend.setdefault(
            event.canonical(),
            _Resend(
                signed,
                self._clock() + self.RESEND_FIRST_SECONDS,
                self.RESEND_FIRST_SECONDS,
                self._clock(),
            ),
        )
        return DriverOutput(broadcasts=(encode_vote_request(signed),))

    def record_evidence(self, signed: SignedTransfer) -> bool:
        """
        Keep a signed event as evidence, with no vote and no execution. This is what
        arrives by the paths that used to execute. True if it was kept, also after
        a halt: a proof of equivocation is still worth having then.
        """
        if not self._is_authorized(signed):
            return False

        self._record_signed(signed)
        return True

    def _handle_vote_request(self, signed: SignedTransfer) -> DriverOutput:
        # The cheap check first: a request this node would refuse anyway costs no signature.
        if self._closing is not None or not self._is_admitted(signed.transfer):
            return _NOTHING

        if not self._is_authorized(signed):
            self._cost += BAD_SIGNATURE_COST
            return _NOTHING

        # Before the replica, because a vote refused is when the proof appears.
        self._record_signed(signed)
        self.rounds.learn(signed)
        vote = self.replica.handle_vote_request(signed.transfer, signed)

        if vote is None:
            return _NOTHING

        self.rounds.voted_round_0(signed.transfer)
        return DriverOutput(replies=(encode_vote(signed.transfer, vote),))

    def _handle_vote(self, event: Transfer, vote: Vote) -> DriverOutput:
        aggregating = self._aggregating.get(event.canonical())

        # A halt empties the aggregation, so nothing is found here after one.
        if aggregating is None:
            return _NOTHING

        event, votes = aggregating

        if not self.committee.has_validator(vote.validator):
            self._cost += BAD_SIGNATURE_COST
            LOG.warning(
                "vote.rejected",
                extra={
                    "reason": "validator_outside_committee_epoch",
                    "validator": vote.validator,
                    "epoch": self.committee.epoch,
                    "sender": event.sender,
                    "nonce": event.nonce,
                },
            )
            return _NOTHING

        if not vote.verify(self.committee, event):
            self._cost += BAD_SIGNATURE_COST
            return _NOTHING

        # By validator, so that the same one twice counts once (idempotent).
        votes[vote.validator] = vote
        return DriverOutput(broadcasts=tuple(self._complete(event, votes)))

    def _complete(
        self,
        event: Transfer,
        votes: dict[int, Vote],
    ) -> list[dict]:
        """
        With `2f+1` votes of round 0, a prepare certificate: sent, and the precommits follow. With all
        `n`, a decision (the fast path). The votes are gathered until one of the two decides.
        """
        if len(votes) < self.committee.quorum:
            return []

        certificate = QuorumCertificate(
            event,
            tuple(votes[validator] for validator in sorted(votes)),
            self.committee.epoch,
        )
        committee = self.committee

        if certificate.decides(committee):
            self._aggregating.pop(event.canonical(), None)
            self._to_resend.pop(event.canonical(), None)
            return [encode_certificate(certificate), *self._take_decision(certificate)]

        if (event.sender, event.nonce, 0) in self._prepares:
            return []

        # Asking again cannot help any more: the precommits, and if need be the rounds, decide.
        self._to_resend.pop(event.canonical(), None)
        signed = self.rounds.signed.get(event.event_id())
        return [encode_certificate(certificate, signed), *self._take_prepare(certificate)]

    def _handle_certificate(self, certificate: QuorumCertificate) -> DriverOutput:
        if self.halted:
            return _NOTHING

        if not self.replica.certificate_is_valid(certificate):
            self._cost += BAD_SIGNATURE_COST
            return _NOTHING

        if certificate.decides(self.replica.committee_of(certificate)):
            return DriverOutput(broadcasts=tuple(self._take_decision(certificate)))

        if certificate.epoch != self.committee.epoch:
            return _NOTHING

        return DriverOutput(broadcasts=tuple(self._take_prepare(certificate)))

    def _take_prepare(self, certificate: QuorumCertificate) -> list[dict]:
        """A valid prepare certificate of this epoch. Halt on another of the same round."""
        event = certificate.event
        key = (event.sender, event.nonce, certificate.round)
        known = self._prepares.get(key)

        if known is not None:
            if known.event.canonical() != event.canonical():
                self.replica.record_halt(known, certificate)
                self._halted_now()
            return []

        self._prepares[key] = certificate
        return self.rounds.prepare(certificate)

    def _take_decision(self, certificate: QuorumCertificate) -> list[dict]:
        """A valid decision: executed when it can run, and the rounds of its key stop."""
        event = certificate.event
        self._aggregating.pop(event.canonical(), None)
        self._to_resend.pop(event.canonical(), None)
        taken = self._accept(certificate)

        if not taken or self.halted or certificate.epoch != self.committee.epoch:
            return []

        signed = self.rounds.signed.get(event.event_id()) or self.signed_events.get(event.event_id())
        if signed is not None and signed.transfer.canonical() == event.canonical():
            self.replica.record_round_evidence(signed)
        elif self.rounds.enabled:
            LOG.warning(
                "decided without its sender's signature: not in the report of this node",
                extra={"sender": event.sender, "nonce": event.nonce},
            )

        return self.rounds.decided(certificate)

    def _undecided_votes(self) -> bool:
        """A key this node voted on or takes part in the rounds of, with no decision yet."""
        if not self.rounds.enabled:
            return False
        return any(state["decided"] is None for _, _, state in self.replica.round_states())

    # How long a member waits, after an order to close, for the keys it voted on to be decided.
    CLOSING_GRACE_SECONDS = 8.0

    def _report(self, change: EpochChange) -> EpochReport | None:
        """The report of this node for `change`, or None while it waits for its keys to be decided."""
        if self._closing is None or self._closing.change_id != change.change_id:
            self._closing_since = self._clock()
            # The keys it voted on that are still open: the others hear of them now, not at a timeout.
            self._pending_reports = self.rounds.hurry()
        waited = self._clock() - self._closing_since
        if self._undecided_votes() and waited < self.CLOSING_GRACE_SECONDS:
            self._closing = change
            return None
        self._closing = None
        return self.replica.report_epoch(change)

    def _halted_now(self) -> None:
        self._buffer.clear()
        self._waiting.clear()
        self._aggregating.clear()

    def _accept(self, certificate: QuorumCertificate) -> bool:
        """
        The certificate is valid. Halt on a conflict, or try to execute it. True if this node took it,
        also if it held it already, and False if there is no room for it now.
        """
        event = certificate.event
        key = (event.sender, event.nonce)

        known = self._known.get(key)

        if known is not None and known.event.canonical() != event.canonical():
            # A conflict over an ended committee says only that its keys were stolen, and it
            # concerns a sender that signed both versions, since both are in the locks. It must
            # not stop this node: what it holds stays.
            if certificate.epoch < self.committee.epoch:
                LOG.warning(
                    "conflicting certificate of an ended committee ignored",
                    extra={"sender": event.sender, "nonce": event.nonce, "epoch": certificate.epoch},
                )
                return False

            self.replica.record_halt(known, certificate)
            self._halted_now()
            return False

        if known is None and self.replica.is_covered(event):
            # Pruned, or never held. Nothing can run under the snapshot in any case. Without the
            # other certificate there is no proof to halt on, and this is the limit of pruning.
            if not self.replica.has_executed_id(event.event_id()):
                LOG.critical(
                    "valid certificate conflicts with a snapshot",
                    extra={"sender": event.sender, "nonce": event.nonce},
                )

            return False

        if known is None:
            # Lean spec (formal/lean/PSystem/Quorum.lean, certificate): execution
            # requires certValid && executableBool && r17Ready && !executed. A valid
            # certificate for a statically non-executable event is accepted as known
            # (idempotent/conflict-tracked) but never buffered/executed.
            # Durable before anything else: a restart that lost it could not see a conflict with it.
            self.replica.hold_decided(certificate)

            if not is_executable_event(event):
                self._known[key] = certificate
                LOG.info(
                    "valid certificate for a statically non-executable event accepted (not executed)",
                    extra={"sender": event.sender, "nonce": event.nonce},
                )
                return True

            if not self._has_room_for(event):
                self.certificates_left_out += 1
                return False

            event_id = event.event_id()
            self._known[key] = certificate
            self._buffer[event_id] = certificate
            self._waiting.setdefault(event.sender, {})[event.nonce] = event_id

        self._retry_buffer()
        return True

    def _has_room_for(self, event: Transfer) -> bool:
        expected = self.replica.state.nonce(event.sender)

        # The next nonce of a sender may be able to run, and that never waits for room.
        if event.nonce <= expected:
            return True

        if self.max_nonce_ahead is not None and event.nonce > expected + self.max_nonce_ahead:
            return False

        return len(self._buffer) < self.max_buffered

    def _no_longer_waiting(self, event_id: str) -> None:
        event = self._buffer.pop(event_id).event
        nonces = self._waiting[event.sender]
        del nonces[event.nonce]

        if not nonces:
            del self._waiting[event.sender]

    def _retry_buffer(self) -> None:
        # Always the smallest id that can run, so that what waits here runs in one order however it
        # arrived. When each certificate arrives can still change the order in the log of a node. Only
        # the next nonce of each sender can run, so what waits further on costs nothing here. One that cannot run yet is tried again after anything else runs, since that may
        # bring it funds or a parent. A failed write leaves the certificate here, and any later
        # certificate tries it again.
        state = self.replica.state
        ready = [
            nonces[state.nonce(sender)]
            for sender, nonces in self._waiting.items()
            if state.nonce(sender) in nonces
        ]
        heapq.heapify(ready)
        blocked = []

        while ready:
            event_id = heapq.heappop(ready)
            certificate = self._buffer[event_id]

            if not self.replica.handle_certificate(certificate):
                blocked.append(event_id)
                continue

            self._no_longer_waiting(event_id)
            following = self._waiting.get(certificate.event.sender, {}).get(
                self.replica.state.nonce(certificate.event.sender)
            )

            if following is not None:
                heapq.heappush(ready, following)

            for waiting in blocked:
                heapq.heappush(ready, waiting)

            blocked = []

    @staticmethod
    def _is_authorized(signed: SignedTransfer) -> bool:
        return is_authorized_transfer(signed)

    def _is_admitted(self, event: Transfer) -> bool:
        state = self.replica.state
        expected = state.nonce(event.sender)

        if self.max_nonce_ahead is not None and not (
            expected <= event.nonce <= expected + self.max_nonce_ahead
        ):
            return False

        # A sender with no funds at all is who costs the most for the least. Funds that are
        # on their way are not refused: only a sender with none now and none known.
        if self.require_funds and state.balance(event.sender) == 0:
            return False

        return True

    def _record_signed(self, signed: SignedTransfer) -> None:
        # Evidence in memory, which the protocol does not need. Past the limit it is not kept.
        if self.max_evidence is not None and len(self.signed_events) >= self.max_evidence:
            return

        event = signed.transfer
        key = (event.sender, event.nonce)

        if event.event_id() not in self.signed_events:
            self.signed_events[event.event_id()] = signed
            self._unpublished_signed.append(signed)

        first = self._first_signed.setdefault(key, signed)

        if (
            first.transfer.canonical() != event.canonical()
            and key not in self.equivocations
        ):
            self.equivocations[key] = EquivocationProof(first, signed)
            self._unpublished_proofs.append(self.equivocations[key])

    def new_signed_events(self) -> dict[str, SignedTransfer]:
        """What was kept since the last call: the node publishes it with no copy of the rest."""
        new = {signed.transfer.event_id(): signed for signed in self._unpublished_signed}
        self._unpublished_signed = []
        return new

    def new_equivocations(self) -> list[EquivocationProof]:
        new = self._unpublished_proofs
        self._unpublished_proofs = []
        return new
