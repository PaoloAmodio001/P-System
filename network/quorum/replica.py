"""
The rules of the model on top of the store: votes, certificates, execution, epochs and snapshots. No network.

Quorum mode: docs/FORMAL-SPECIFICATION.md, section 13.1. The model is in formal/lean/PSystem/Quorum.lean.
"""

from collections.abc import Callable

from core.attestation import (
    Committee,
    EpochChange,
    EpochClosure,
    EpochReport,
    QuorumCertificate,
    RoundProposal,
    RoundReport,
    Snapshot,
    SnapshotAttestation,
    PRECOMMIT,
    VOTE,
    Vote,
    is_well_formed_event,
    phase_payload,
)
from core.event import Transfer
from core.signed_event import SignedTransfer
from core.state import State
from crypto.identity import Identity
from network.remote_signer import SignerUnavailable
from network.quorum.common import (
    LOG,
    VoteStoreError,
)
from network.message import decode_certificate, encode_certificate
from network.quorum import lean_core
from network.quorum.store import SqliteVoteStore


class QuorumReplica:
    """
    The protocol of an honest node: `step` in formal/lean/PSystem/Quorum.lean.

    `handle_vote_request` is the `voteRequest` branch and `handle_certificate` the
    `certificate` branch. An input that is refused changes nothing, so delivering
    it again is the same as trying again, and the model needs no buffer.

    The signing key stays here, and the only path to a signature goes through the
    vote lock. That, together with Ed25519, is what the hypothesis `Unforgeable`
    means for this code.

    Not thread-safe: the caller serializes the calls.
    """

    def __init__(
        self,
        identity: Identity,
        initial_state: State,
        store: SqliteVoteStore,
        auth: Callable[[Transfer], bool],
    ) -> None:
        if identity.public_key != store.validator:
            raise ValueError("VOTE STORE BELONGS TO ANOTHER VALIDATOR")

        if initial_state.root() != store.committee.genesis_root:
            raise ValueError("INITIAL STATE IS NOT THE GENESIS OF THE COMMITTEE")

        self._identity = identity
        self._store = store
        self._auth = auth
        self._initial_state = initial_state
        self.state = initial_state.copy()
        self.log: list[QuorumCertificate] = []
        # Steps of `_derives_snapshot` so far: see `QuorumDriver._handle_snapshot_request`.
        self.derive_steps = 0
        # The same certificates by event id, so that a client asking for one does not scan the log.
        self._log_by_id: dict[str, QuorumCertificate] = {}
        self._executed_ids: set[str] = set()
        self.nonce_locked_permanently_total = 0
        # What the state started from, if not the genesis: signatures over these events are not read
        # again, which is the whole cost of a restart. `resume_is_derive` says nothing is lost.
        self.base = store.snapshot()

        if self.base is not None:
            # This node checked it when it took it, also if it was signed before version 2.
            if not self._snapshot_is_good(self.base, allow_legacy=True):
                raise VoteStoreError("SNAPSHOT DOES NOT VERIFY")

            self.state = self.base.state.copy()
            self._executed_ids = set(self.base.ids)

        for certificate in store.certificates():
            if self.is_covered(certificate.event):
                if certificate.event.event_id() not in self._executed_ids:
                    raise VoteStoreError("LOG OF CERTIFICATES DOES NOT FIT THE SNAPSHOT")

                self.log.append(certificate)
                self._log_by_id[certificate.event.event_id()] = certificate
                continue

            rows = self._execution(certificate, old_keys=False)
            if rows is None:
                raise VoteStoreError("LOG OF CERTIFICATES DOES NOT REPLAY")
            self._execute(certificate, rows)

    @property
    def initial_state(self) -> State:
        """The genesis state: what an empty log starts from."""
        return self._initial_state

    @property
    def committee(self) -> Committee:
        """The committee in force, which changes when a closure is installed."""
        return self._store.committee

    @property
    def executed_count(self) -> int:
        """All it executed, also what it has pruned or got inside a snapshot."""
        return len(self._executed_ids)

    def is_covered(self, event: Transfer) -> bool:
        return self.base is not None and event.nonce < self.base.floor(event.sender)

    def has_executed_id(self, event_id: str) -> bool:
        return event_id in self._executed_ids

    def executed_since_base(self) -> int:
        start = self._initial_state if self.base is None else self.base.state
        return sum(self.state.nonces.values()) - sum(start.nonces.values())

    def _snapshot_is_good(self, snapshot: Snapshot, allow_legacy: bool = False) -> bool:
        committee = self._store.committee_at(snapshot.epoch)
        return (
            committee is not None
            and snapshot.verify(committee, allow_legacy)
            # Each execution moves one nonce by one, so the two counts must agree.
            and len(snapshot.ids)
            == sum(snapshot.state.nonces.values()) - sum(self._initial_state.nonces.values())
        )

    def candidate_snapshot(self) -> Snapshot:
        return Snapshot(self.committee.epoch, self.state.copy(), tuple(sorted(self._executed_ids)))

    def _derives_snapshot(self, digest: str, nonces: dict[str, int]) -> bool:
        """
        What an honest member checks before signing: `Attests` in the model. It holds the events
        under `nonces` and they come to this digest. A member behind says no and the proposer asks
        again. One that pruned past `nonces` starts from its base, so it comes to this digest only
        if this is its base. The state decides by itself, whatever is left out: `ids` count too.
        """
        start = self._initial_state if self.base is None else self.base.state

        # What this would come to anyway. It saves a pass over the log for each request sent again.
        if any(self.state.nonce(sender) < nonce for sender, nonce in nonces.items()):
            return False

        # The work done, which the driver charges to the peer that asked.
        self.derive_steps += len(self.log)
        pending = [
            certificate.event
            for certificate in self.log
            if start.nonce(certificate.event.sender)
            <= certificate.event.nonce
            < nonces.get(certificate.event.sender, 0)
        ]
        state = start.copy()
        ids = set() if self.base is None else set(self.base.ids)
        progress = True

        # A part of a valid order may need another order: funds come from what is left out.
        while pending and progress:
            progress = False
            waiting = []
            self.derive_steps += len(pending)

            for event in pending:
                rows = self._runs_on(state, ids, event)
                if rows is not None:
                    self._apply_rows(state, rows)
                    ids.add(event.event_id())
                    progress = True
                else:
                    waiting.append(event)

            pending = waiting

        return Snapshot(self.committee.epoch, state, tuple(sorted(ids))).digest == digest

    def attest_snapshot(
        self,
        epoch: int,
        digest: str,
        nonces: dict[str, int],
    ) -> SnapshotAttestation | None:
        if (
            not self.is_member
            or self._store.halted()
            or epoch != self.committee.epoch
            or not self._derives_snapshot(digest, nonces)
        ):
            return None

        locks = self._store.locks_over(nonces)

        if locks is None:
            LOG.warning("a lock from an older store has no signature of its sender: no snapshot signed")
            return None

        try:
            return SnapshotAttestation.create(self.committee, self._identity, digest, locks)
        except SignerUnavailable as error:
            LOG.error("signer gave no signature", extra={"reason": str(error)})
            return None

    def install_snapshot(self, snapshot: Snapshot) -> bool:
        """
        Start from this snapshot and go on with what this node has beyond it. True if it did. It comes
        from a committee this node holds, and the one in force unless it is this node's own file: the
        keys of an ended committee can be stolen. The order of the log does not change. An event still
        runs after what it ran after, or sooner, with the same debits and more credits.
        """
        if (
            snapshot.epoch != self.committee.epoch
            or not self._snapshot_is_good(snapshot)
            or (
                self.base is not None
                and self.base.digest == snapshot.digest
                and self.base.epoch == snapshot.epoch
                and not self.base.is_legacy
            )
            or (
                self.base is not None
                and any(
                    snapshot.floor(sender) < nonce
                    for sender, nonce in self.base.state.nonces.items()
                )
            )
        ):
            return False

        state = snapshot.state.copy()
        ids = set(snapshot.ids)

        for certificate in self.log:
            event = certificate.event

            if event.nonce < snapshot.floor(event.sender):
                if event.event_id() in ids:
                    continue

                # At most `f` faulty cannot do this: `no_double_spend`. This node keeps what it has.
                LOG.critical(
                    "snapshot does not hold an event this node executed",
                    extra={"sender": event.sender, "nonce": event.nonce},
                )
                return False

            rows = self._runs_on(state, ids, event)
            if rows is None:
                LOG.critical(
                    "the log of this node does not run after a snapshot",
                    extra={"sender": event.sender, "nonce": event.nonce},
                )
                return False

            self._apply_rows(state, rows)
            ids.add(event.event_id())

        self._store.record_snapshot(snapshot)
        self.base = snapshot
        self.state = state
        self._executed_ids = ids
        return True

    def prune_covered(self) -> list[QuorumCertificate]:
        """Drop the certificates the snapshot covers, on disk first. Returns what went."""
        covered = [c for c in self.log if self.is_covered(c.event)]

        if covered:
            self._store.forget_certificates([c.event.event_id() for c in covered])
            self.log = [c for c in self.log if not self.is_covered(c.event)]

            for certificate in covered:
                self._log_by_id.pop(certificate.event.event_id(), None)

        return covered

    def apply_floor(self) -> None:
        if self.base is not None:
            self._store.apply_floor(self.base)

    @property
    def is_member(self) -> bool:
        return self.committee.index_of(self._identity.public_key) is not None

    def certificate_is_valid(self, certificate: QuorumCertificate) -> bool:
        """
        The signatures verify, and for a committee that has ended, the event is in the locks.
        Keys of an ended committee can be stolen, and with enough of them any signature verifies.
        Everything really certified in an epoch is in the locks of the next one
        (`closure_preserves_certified`), so this loses nothing real: `QuorumOldKeys.lean`.
        """
        return certificate.verify(self._store.committee_of(certificate)) and (
            certificate.epoch >= self.committee.epoch
            or self._store.is_locked_event(certificate.event)
        )

    def certificate_was_valid(self, certificate: QuorumCertificate) -> bool:
        """For the log of this node, read back: it passed the rule above when it arrived."""
        return certificate.verify(self._store.committee_of(certificate))

    @property
    def executed(self) -> list[Transfer]:
        return [certificate.event for certificate in self.log]

    def votes(self) -> list[Transfer]:
        """Read from the store: what counts is what would survive a restart."""
        return self._store.votes()

    def halted(self) -> bool:
        return self._store.halted()

    def record_halt(
        self,
        first: QuorumCertificate,
        second: QuorumCertificate,
    ) -> None:
        self._store.record_halt(first, second)
        LOG.critical(
            "node halted: two valid certificates in conflict",
            extra={"sender": first.event.sender, "nonce": first.event.nonce},
        )

    def halt_proof(self) -> tuple[QuorumCertificate, QuorumCertificate] | None:
        return self._store.halt_proof()

    def handle_vote_request(
        self,
        event: Transfer,
        signed: SignedTransfer | None = None,
        gathering: bool = False,
    ) -> Vote | None:
        """
        Return a vote, or None if the event is refused. The signature comes after
        the vote is durably recorded. If that fails the error propagates, and no
        signature exists.
        """
        if not is_well_formed_event(event):
            return None

        if not self._auth(event):
            return None

        if not self.is_member:
            return None

        # Lean spec (formal/lean/PSystem/Quorum.lean, voteRequest): vote is admitted
        # by `auth && voteAllowed`, independent of static/state executability.
        # Executability is enforced at certificate execution (executableBool/r17Ready).
        #
        # With rounds, the vote of round 0 is also the input `request` of `Rounds.step`, and the two
        # are written together: a validator that has left round 0 for this key casts no vote of round
        # 0, since its reports say it has none (`report_vote0'`).
        round_state = None
        if self.has_rounds:
            before = self._store.round_state(event.sender, event.nonce)
            model_before = None if before is None else {
                k: v for k, v in before.items() if not k.startswith("_")
            }
            round_state = lean_core.step(
                self.committee.n,
                self.committee.f,
                model_before,
                {"kind": "request", "value": event.event_id()},
            )
            if round_state["vote0"] != event.event_id():
                return None
            if before is not None and "_best" in before:
                round_state["_best"] = before["_best"]

        if not self._store.record_vote(event, signed, gathering, round_state):
            return None

        return self._signed_vote(event)

    @property
    def has_rounds(self) -> bool:
        """Rounds run with `n = 3f+1`. With the optional `5f+1` a split waits for the end of the epoch."""
        return not self.committee.unlock

    def round_state(self, sender: str, nonce: int) -> dict | None:
        return self._store.round_state(sender, nonce)

    def round_states(self) -> list[tuple[str, int, dict]]:
        return self._store.round_states()

    def round_step(
        self,
        sender: str,
        nonce: int,
        entry: dict,
        certificate: QuorumCertificate | None = None,
    ) -> tuple[dict | None, dict] | None:
        """
        One input of `Rounds.step` for a key, run by the compiled model, and written before
        anything it allows is signed. The states before and after, or None if this node signs
        nothing more in this epoch (halted or closed).

        With the state goes the certificate of its highest prepare (`certificate`, for the input
        `prepared`): a report must show it, also after a restart (`precommit_report`).
        """
        before = self._store.round_state(sender, nonce)
        model_before = None if before is None else {k: v for k, v in before.items() if not k.startswith("_")}
        after = lean_core.step(self.committee.n, self.committee.f, model_before, entry)

        if before is not None and "_best" in before:
            after["_best"] = before["_best"]
        if certificate is not None and after["best"] != (None if model_before is None else model_before["best"]):
            after["_best"] = encode_certificate(certificate)

        if after != before and not self._store.record_round_state(sender, nonce, after):
            return None

        return before, after

    @staticmethod
    def best_certificate(state: dict | None) -> QuorumCertificate | None:
        """The certificate of the highest prepare of a state written by `round_step`."""
        if state is None or "_best" not in state:
            return None
        return decode_certificate(state["_best"])

    def own_vote0(self, sender: str, nonce: int) -> SignedTransfer | None:
        """This validator's vote of round 0 for a key, with its sender's signature."""
        return self._store.signed_vote(sender, nonce)

    def sign_phase(self, event: Transfer, phase: str, round_: int) -> Vote | None:
        """A vote of a later round or a precommit that `round_step` allowed. None without a signer."""
        try:
            return Vote.create_phase(self.committee, self._identity, event, phase, round_)
        except SignerUnavailable as error:
            LOG.error("signer gave no signature", extra={"reason": str(error)})
            return None

    def sign_report(
        self,
        sender: str,
        nonce: int,
        round_: int,
        vote0: SignedTransfer | None,
        best: QuorumCertificate | None,
        best_value: SignedTransfer | None = None,
    ) -> RoundReport | None:
        try:
            return RoundReport.create(
                self.committee, self._identity, sender, nonce, round_, vote0, best, best_value
            )
        except SignerUnavailable as error:
            LOG.error("signer gave no signature", extra={"reason": str(error)})
            return None

    def sign_proposal(
        self,
        round_: int,
        value: SignedTransfer,
        reports: tuple[RoundReport, ...],
    ) -> RoundProposal | None:
        try:
            return RoundProposal.create(self.committee, self._identity, round_, value, reports)
        except SignerUnavailable as error:
            LOG.error("signer gave no signature", extra={"reason": str(error)})
            return None

    def hold_decided(self, certificate: QuorumCertificate) -> None:
        self._store.hold_decided(certificate)

    def record_round_evidence(self, signed: SignedTransfer) -> None:
        self._store.record_round_evidence(signed)

    def decided_held(self) -> list[QuorumCertificate]:
        return self._store.decided_held()

    def gathering(self) -> list[SignedTransfer]:
        return self._store.gathering()

    def forget_gathering(self, event_ids: list[str]) -> None:
        self._store.forget_gathering(event_ids)

    def _signed_vote(self, event: Transfer) -> Vote | None:
        """
        With a signer in another process, it can refuse or be away. No signature then: the
        same as no vote, and a request sent again asks again, since the vote stays recorded.
        """
        try:
            return Vote.create(self.committee, self._identity, event)
        except SignerUnavailable as error:
            LOG.error("signer gave no signature", extra={"reason": str(error)})
            return None

    def report_epoch(self, change: EpochChange) -> EpochReport | None:
        """
        Stop voting and report, durably in that order. None if this node has no vote in this epoch,
        because it is not a member of the committee, or if it already reported for another order.
        """
        if not self.is_member or self._store.halted() or self._store.is_restored():
            return None

        votes = self._store.close_epoch(change)

        if votes is None:
            return None

        try:
            return EpochReport.create(self.committee, self._identity, change.change_id, votes)
        except SignerUnavailable as error:
            LOG.error("signer gave no signature", extra={"reason": str(error)})
            return None

    def reported_change(self) -> EpochChange | None:
        return self._store.reported_change()

    def install_closure(self, closure: EpochClosure) -> None:
        closing = self._store.committee
        epoch = closing.epoch
        self._store.install_closure(closure)
        self._log_permanently_locked_nonces(closing, closure, epoch)

    def _log_permanently_locked_nonces(
        self,
        committee: Committee,
        closure: EpochClosure,
        epoch: int,
    ) -> None:
        by_key: dict[tuple[str, int], dict[bytes, int]] = {}
        for report in closure.reports:
            seen: set[tuple[tuple[str, int], bytes]] = set()
            for signed in report.votes:
                event = signed.transfer
                key = (event.sender, event.nonce)
                canonical = event.canonical()
                marker = (key, canonical)
                if marker in seen:
                    continue
                seen.add(marker)
                by_key.setdefault(key, {})
                by_key[key][canonical] = by_key[key].get(canonical, 0) + 1

        if committee.unlock:
            threshold = 2 * committee.f + 1
            for (sender, nonce), counts in sorted(by_key.items()):
                supported = sum(1 for n in counts.values() if n >= threshold)
                if len(counts) > 1 and supported == 0:
                    # split but freed by unlock (not permanently locked)
                    LOG.info(
                        "nonce.split_unlocked",
                        extra={
                            "sender": sender,
                            "nonce": nonce,
                            "epoch": epoch,
                            "divergent_votes": sum(counts.values()),
                            "versions": len(counts),
                        },
                    )
            return

        for (sender, nonce), counts in sorted(by_key.items()):
            if len(counts) <= 1:
                continue
            divergent = sum(counts.values())
            self.nonce_locked_permanently_total += 1
            LOG.error(
                "nonce.locked_permanently",
                extra={
                    "sender": sender,
                    "nonce": nonce,
                    "epoch": epoch,
                    "reason": "split_votes_no_unlock",
                    "divergent_votes": divergent,
                    "versions": len(counts),
                },
            )

    def committee_before_last(self) -> Committee:
        return self._store.committee_at(self.committee.epoch - 1)

    def group(self):
        return self._store.group()

    def committee_of(self, certificate: QuorumCertificate) -> Committee:
        return self._store.committee_of(certificate)

    def closures(self, after_epoch: int = 0) -> list[EpochClosure]:
        return self._store.closures(after_epoch)

    def handle_certificate(self, certificate: QuorumCertificate) -> bool:
        """
        Execute the certificate if it can run now. True if it was executed. A
        halted node executes nothing. That check is here and not in `_execution`,
        because the log replayed at a restart holds what ran before the halt.
        """
        if self._store.halted():
            return False

        rows = self._execution(certificate, old_keys=True)
        if rows is None:
            return False

        # On disk first: if this fails, the state has not changed.
        self._store.append_certificate(certificate)
        self._execute(certificate, rows)
        return True

    # --- Execution: the Lean core decides --------------------------------------------------------
    #
    # Whether a certificate executes, and what it does to the state, is `executes` and `ApplyEvent`
    # of `formal/lean/PSystem/CoreExec.lean`, called through `lean_core.execute`. Python hands over
    # what the theorems there say is enough: the rows of the sender and the receiver, the executed ids
    # among the event and its parents, and the result of checking each signature. What stays here
    # is outside the model: the types of the fields, Ed25519, the epoch of the certificate, and the
    # rule on keys of ended committees (`QuorumOldKeys.lean`).

    def _decision_quorum(self, committee: Committee, phase: str) -> int | None:
        """How many valid signers a certificate of this phase needs to decide, or None if it never does."""
        if committee.unlock:
            return committee.quorum if phase == VOTE else None
        if phase == PRECOMMIT:
            return committee.quorum
        if phase == VOTE:
            return committee.n
        return None

    def _checks(self, certificate: QuorumCertificate, quorum: int, committee: Committee) -> list | None:
        """
        `[member, verified]` for each vote, or None when the certificate has what the model cannot
        hold (a signer outside the committee, a field of the wrong type). Signatures are checked only
        when the signers could make a decision: otherwise the answer is no whatever they are.
        """
        if type(certificate.epoch) is not int or certificate.epoch != committee.epoch:
            return None
        if type(certificate.votes) is not tuple or not all(type(v) is Vote for v in certificate.votes):
            return None
        signers = [vote.validator for vote in certificate.votes]
        if not all(committee.has_validator(signer) for signer in signers):
            return None
        if len(set(signers)) != len(signers) or len(signers) < quorum:
            return [[signer, False] for signer in signers]
        try:
            payload = phase_payload(committee, certificate.phase, certificate.round, certificate.event)
        except (ValueError, TypeError, AttributeError):
            return None
        return [[vote.validator, vote._verify_payload(committee, payload)] for vote in certificate.votes]

    def _execution(self, certificate: QuorumCertificate, old_keys: bool) -> list | None:
        """The rows of the two accounts after the certificate if it executes now, else None."""
        event = certificate.event
        if not is_well_formed_event(event):
            return None
        if old_keys and not (
            certificate.epoch >= self.committee.epoch or self._store.is_locked_event(event)
        ):
            return None
        committee = self._store.committee_of(certificate)
        quorum = self._decision_quorum(committee, certificate.phase)
        if quorum is None:
            return None
        checks = self._checks(certificate, quorum, committee)
        if checks is None:
            return None
        return self._core_execute(committee.n, quorum, self.state, self._executed_ids, event, checks)

    @staticmethod
    def _core_execute(n: int, quorum: int, state: State, ids: set[str], event: Transfer, checks: list):
        rows = [[account, state.balance(account), state.nonce(account)] for account in (event.sender, event.receiver)]
        known = [x for x in (event.event_id(), *event.parents) if x in ids]
        return lean_core.execute(n, quorum, rows, known, event, checks)

    @classmethod
    def _runs_on(cls, state: State, ids: set[str], event: Transfer) -> list | None:
        """An event of the log, whose certificate was valid: a certificate of no signers needs none."""
        if not is_well_formed_event(event):
            return None
        return cls._core_execute(1, 0, state, ids, event, [])

    @staticmethod
    def _apply_rows(state: State, rows: list) -> None:
        # Balances of both, as `StateDeriver` writes them; a nonce only where it moved, so that an
        # account that only receives keeps no nonce entry, as before.
        for account, balance, nonce in rows:
            state.balances[account] = balance
            if state.nonce(account) != nonce:
                state.nonces[account] = nonce

    def certificate_of(self, event_id: str) -> QuorumCertificate | None:
        """The certificate of an event this node executed and still holds, without reading the log."""
        return self._log_by_id.get(event_id)

    def _execute(self, certificate: QuorumCertificate, rows: list) -> None:
        self._apply_rows(self.state, rows)
        self.log.append(certificate)
        self._log_by_id[certificate.event.event_id()] = certificate
        self._executed_ids.add(certificate.event.event_id())
