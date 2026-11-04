"""
Quorum mode: docs/FORMAL-SPECIFICATION.md, section 13.1.

The model is in formal/lean/PSystem/Quorum.lean. The link between the two is
empirical, not a refinement proof.
"""

import json
import os
import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from core.attestation import (
    Committee,
    QuorumCertificate,
    Vote,
    is_well_formed_event,
)
from core.derive import StateDeriver
from core.event import Transfer
from core.equivocation import EquivocationProof
from core.signed_event import SignedTransfer
from core.state import State
from crypto.identity import Identity
from network.message import (
    decode_certificate,
    decode_certificate_sync,
    decode_certificate_sync_request,
    decode_vote,
    decode_vote_request,
    encode_certificate,
    encode_certificate_sync,
    encode_certificate_sync_request,
    encode_vote,
    encode_vote_request,
)


class VoteStoreError(Exception):
    """
    The store cannot be trusted or could not record a write.

    Not a ValueError on purpose: a caller must not treat a failure to record as a
    malformed message. No signature may follow it.
    """


_SCHEMA_VERSION = "2"
_PREVIOUS_SCHEMA_VERSION = "1"

# One row at most: the first proof stays, and any other says the same thing.
_HALT_TABLE = """
    CREATE TABLE halt (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        first_canonical TEXT NOT NULL,
        first_signatures TEXT NOT NULL,
        second_canonical TEXT NOT NULL,
        second_signatures TEXT NOT NULL
    )
"""

_SCHEMA = (
    """
    CREATE TABLE meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    # The nonce is text because Lean nonces are unbounded and an SQLite integer
    # has 64 bits. It is only compared for equality.
    """
    CREATE TABLE votes (
        sender TEXT NOT NULL,
        nonce TEXT NOT NULL,
        event_id TEXT NOT NULL UNIQUE,
        canonical TEXT NOT NULL,
        PRIMARY KEY (sender, nonce)
    )
    """,
    """
    CREATE TABLE certificates (
        position INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT NOT NULL UNIQUE,
        canonical TEXT NOT NULL,
        signatures TEXT NOT NULL
    )
    """,
    _HALT_TABLE,
)


def _event_from_canonical(canonical: str) -> Transfer:
    data = json.loads(canonical)
    return Transfer(
        sender=data["sender"],
        receiver=data["receiver"],
        amount=data["amount"],
        nonce=data["nonce"],
        parents=tuple(data["parents"]),
    )


def _encode_signatures(certificate: QuorumCertificate) -> str:
    return json.dumps(
        [[vote.validator, vote.signature.hex()] for vote in certificate.votes],
        separators=(",", ":"),
    )


def _certificate_from_row(canonical: str, signatures: str) -> QuorumCertificate:
    return QuorumCertificate(
        _event_from_canonical(canonical),
        tuple(
            Vote(validator, bytes.fromhex(signature))
            for validator, signature in json.loads(signatures)
        ),
    )


def _is_halt_proof(
    committee: Committee,
    first: QuorumCertificate,
    second: QuorumCertificate,
) -> bool:
    """
    Two valid certificates for different alternatives of one `(sender, nonce)`.
    With at most `f` faulty validators this cannot exist: it is what
    `no_double_spend` excludes. `verify` comes first because it never raises, and
    the other checks assume well-formed events.
    """
    return (
        first.verify(committee)
        and second.verify(committee)
        and first.event.sender == second.event.sender
        and first.event.nonce == second.event.nonce
        and first.event.canonical() != second.event.canonical()
    )


class SqliteVoteStore:
    """
    The durable part of a validator: its votes and its log of certificates.

    `record_vote` is the vote lock, `voteAllowed` in the model. When it returns
    True the vote is committed, so a signature may follow; a signature must never
    come first. Losing the votes breaks safety, and a node that does has to be
    counted among the faulty ones. Losing the log does not, because in the model
    votes and log are independent.

    The store also holds the proof of a halt. Once it is recorded, `record_vote`
    refuses and `append_certificate` raises, so a restart cannot forget the halt
    and a process cannot get past it. The state of the halt is read inside the
    transaction of each write, never kept in memory. There is no way out of a halt
    here: that takes a manual intervention. The model has no halt, since `runNode`
    does not stop.

    A missing file is an error unless `create` is true, so that a deleted file
    does not silently become a validator with no votes. This cannot detect an old
    backup put back in place, which is the same loss, nor a proof of a halt deleted
    by hand.
    """

    def __init__(
        self,
        path: Path,
        committee: Committee,
        validator: bytes,
        create: bool = False,
    ) -> None:
        if committee.index_of(validator) is None:
            raise VoteStoreError("VALIDATOR IS NOT A COMMITTEE MEMBER")

        self.committee = committee
        self.validator = validator
        self._lock = threading.RLock()
        self._closed = False
        mode = "rwc" if create else "rw"

        try:
            self._connection = sqlite3.connect(
                f"{Path(path).resolve().as_uri()}?mode={mode}",
                uri=True,
                isolation_level=None,
                check_same_thread=False,
                timeout=30.0,
            )
        except sqlite3.Error as error:
            raise VoteStoreError(f"CANNOT OPEN VOTE STORE: {error}") from error

        try:
            self._configure()
            self._open_schema(committee, validator, create)
        except sqlite3.Error as error:
            self._connection.close()
            raise VoteStoreError(f"INVALID VOTE STORE: {error}") from error
        except VoteStoreError:
            self._connection.close()
            raise

    def _configure(self) -> None:
        # With a rollback journal, EXTRA also syncs the directory after the journal
        # is unlinked. With FULL a power loss right after a commit could bring the
        # journal back and undo a vote whose signature already left.
        self._connection.execute("PRAGMA journal_mode = DELETE").fetchall()
        self._connection.execute("PRAGMA synchronous = EXTRA")

        if self._pragma("journal_mode") != "delete" or self._pragma("synchronous") != 3:
            raise VoteStoreError("VOTE STORE IS NOT DURABLE")

    def _pragma(self, name: str):
        return self._connection.execute(f"PRAGMA {name}").fetchone()[0]

    def _open_schema(
        self,
        committee: Committee,
        validator: bytes,
        create: bool,
    ) -> None:
        expected = {
            "schema_version": _SCHEMA_VERSION,
            "committee_id": committee.committee_id,
            "validator": validator.hex(),
        }

        self._begin()
        try:
            tables = {
                row[0]
                for row in self._connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }

            if not tables:
                if not create:
                    raise VoteStoreError("VOTE STORE WAS NEVER INITIALIZED")

                for statement in _SCHEMA:
                    self._connection.execute(statement)

                self._connection.executemany(
                    "INSERT INTO meta (key, value) VALUES (?, ?)",
                    expected.items(),
                )
                self._connection.execute("COMMIT")
                return

            # A database without this table fails here, as sqlite3.Error.
            found = dict(
                self._connection.execute("SELECT key, value FROM meta").fetchall()
            )
            version = found.pop("schema_version", None)
            del expected["schema_version"]

            if found != expected:
                raise VoteStoreError("VOTE STORE BELONGS TO ANOTHER VALIDATOR")

            if version == _PREVIOUS_SCHEMA_VERSION:
                self._connection.execute(_HALT_TABLE)
                self._connection.execute(
                    "UPDATE meta SET value = ? WHERE key = 'schema_version'",
                    (_SCHEMA_VERSION,),
                )
                self._commit()
            elif version != _SCHEMA_VERSION:
                raise VoteStoreError("UNSUPPORTED VERSION OF THE VOTE STORE")

            self._check_halt_proof()
        finally:
            self._rollback_if_open()

    def _read_halt_proof(self) -> tuple[QuorumCertificate, QuorumCertificate] | None:
        row = self._connection.execute(
            """
            SELECT first_canonical, first_signatures,
                   second_canonical, second_signatures
            FROM halt
            """
        ).fetchone()

        if row is None:
            return None

        return (
            _certificate_from_row(row[0], row[1]),
            _certificate_from_row(row[2], row[3]),
        )

    def _check_halt_proof(self) -> None:
        # A proof that does not verify means the file was altered. Neither ignoring
        # it nor believing it is safe, so the store does not open.
        try:
            proof = self._read_halt_proof()
        except (ValueError, KeyError, TypeError, RecursionError) as error:
            raise VoteStoreError("HALT PROOF IS UNREADABLE") from error

        if proof is not None and not _is_halt_proof(self.committee, *proof):
            raise VoteStoreError("HALT PROOF DOES NOT VERIFY")

    def _is_halted(self) -> bool:
        return (
            self._connection.execute("SELECT 1 FROM halt").fetchone() is not None
        )

    def _begin(self) -> None:
        # IMMEDIATE takes the write lock now, so the check and the write of a
        # vote are one step even for another process with the same file.
        self._connection.execute("BEGIN IMMEDIATE")

    def _commit(self) -> None:
        self._connection.execute("COMMIT")

    def _rollback_if_open(self) -> None:
        if self._connection.in_transaction:
            self._connection.execute("ROLLBACK")

    def _require_open(self) -> None:
        if self._closed:
            raise VoteStoreError("VOTE STORE IS CLOSED")

    def record_vote(self, event: Transfer) -> bool:
        """
        Apply the vote lock. False means that a different event holds the
        `(sender, nonce)` or the id, or that the node has halted, even for an event
        it already voted for. True means that this event is durably recorded,
        possibly by an earlier call.

        Raises instead of returning when nothing can be said about the write;
        no signature may follow an exception.
        """
        canonical = event.canonical().decode()
        event_id = event.event_id()

        with self._lock:
            self._require_open()

            try:
                self._begin()

                if self._is_halted():
                    return False

                existing = {
                    row[0]
                    for row in self._connection.execute(
                        """
                        SELECT canonical FROM votes
                        WHERE (sender = ? AND nonce = ?) OR event_id = ?
                        """,
                        (event.sender, str(event.nonce), event_id),
                    )
                }

                if existing - {canonical}:
                    return False

                if existing:
                    return True

                self._connection.execute(
                    """
                    INSERT INTO votes (sender, nonce, event_id, canonical)
                    VALUES (?, ?, ?, ?)
                    """,
                    (event.sender, str(event.nonce), event_id, canonical),
                )
                self._commit()
                return True
            except sqlite3.Error as error:
                raise VoteStoreError(f"VOTE NOT RECORDED: {error}") from error
            finally:
                self._rollback_if_open()

    def votes(self) -> list[Transfer]:
        with self._lock:
            self._require_open()

            try:
                rows = self._connection.execute(
                    "SELECT canonical FROM votes ORDER BY rowid"
                ).fetchall()
            except sqlite3.Error as error:
                raise VoteStoreError(f"CANNOT READ VOTES: {error}") from error

        return [_event_from_canonical(row[0]) for row in rows]

    def append_certificate(self, certificate: QuorumCertificate) -> None:
        """
        Add an executed certificate to the end of the log. The caller has checked
        it. The same id twice is an error, because a node never executes it twice.
        """
        event = certificate.event
        signatures = _encode_signatures(certificate)

        with self._lock:
            self._require_open()

            try:
                self._begin()

                if self._is_halted():
                    raise VoteStoreError("NODE HAS HALTED")

                self._connection.execute(
                    """
                    INSERT INTO certificates (event_id, canonical, signatures)
                    VALUES (?, ?, ?)
                    """,
                    (event.event_id(), event.canonical().decode(), signatures),
                )
                self._commit()
            except sqlite3.Error as error:
                raise VoteStoreError(f"CERTIFICATE NOT RECORDED: {error}") from error
            finally:
                self._rollback_if_open()

    def certificates(self) -> list[QuorumCertificate]:
        """The log in execution order. Not verified: the caller replays it."""
        with self._lock:
            self._require_open()

            try:
                rows = self._connection.execute(
                    "SELECT canonical, signatures FROM certificates ORDER BY position"
                ).fetchall()
            except sqlite3.Error as error:
                raise VoteStoreError(f"CANNOT READ CERTIFICATES: {error}") from error

        return [
            _certificate_from_row(canonical, signatures)
            for canonical, signatures in rows
        ]

    def record_halt(
        self,
        first: QuorumCertificate,
        second: QuorumCertificate,
    ) -> None:
        """
        Halt the node, durably. Raises ValueError unless the two certificates are
        a proof, so that a forged certificate cannot halt a node: without this one
        message would be enough. Raises VoteStoreError if the write fails, and then
        the node has not halted.

        The two are stored in a fixed order, so the proof does not depend on which
        arrived first. If a proof is already there it stays.
        """
        if not _is_halt_proof(self.committee, first, second):
            raise ValueError("NOT A PROOF OF A HALT")

        low, high = sorted(
            (first, second),
            key=lambda certificate: certificate.event.canonical(),
        )

        with self._lock:
            self._require_open()

            try:
                self._begin()
                self._connection.execute(
                    """
                    INSERT OR IGNORE INTO halt (
                        id,
                        first_canonical, first_signatures,
                        second_canonical, second_signatures
                    )
                    VALUES (1, ?, ?, ?, ?)
                    """,
                    (
                        low.event.canonical().decode(),
                        _encode_signatures(low),
                        high.event.canonical().decode(),
                        _encode_signatures(high),
                    ),
                )
                self._commit()
            except sqlite3.Error as error:
                raise VoteStoreError(f"HALT NOT RECORDED: {error}") from error
            finally:
                self._rollback_if_open()

    def halted(self) -> bool:
        with self._lock:
            self._require_open()

            try:
                return self._is_halted()
            except sqlite3.Error as error:
                raise VoteStoreError(f"CANNOT READ HALT: {error}") from error

    def halt_proof(self) -> tuple[QuorumCertificate, QuorumCertificate] | None:
        """The proof, or None. It was verified when written and when opened."""
        with self._lock:
            self._require_open()

            try:
                return self._read_halt_proof()
            except sqlite3.Error as error:
                raise VoteStoreError(f"CANNOT READ HALT: {error}") from error

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._connection.close()


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
        self.committee = store.committee

        if identity.public_key != store.validator:
            raise ValueError("VOTE STORE BELONGS TO ANOTHER VALIDATOR")

        if initial_state.root() != self.committee.genesis_root:
            raise ValueError("INITIAL STATE IS NOT THE GENESIS OF THE COMMITTEE")

        self._identity = identity
        self._store = store
        self._auth = auth
        self.state = initial_state.copy()
        self.log: list[QuorumCertificate] = []
        self._executed_ids: set[str] = set()

        for certificate in store.certificates():
            if not self._can_execute(certificate):
                raise VoteStoreError("LOG OF CERTIFICATES DOES NOT REPLAY")
            self._execute(certificate)

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

    def halt_proof(self) -> tuple[QuorumCertificate, QuorumCertificate] | None:
        return self._store.halt_proof()

    def handle_vote_request(self, event: Transfer) -> Vote | None:
        """
        Return a vote, or None if the event is refused. The signature comes after
        the vote is durably recorded. If that fails the error propagates, and no
        signature exists.
        """
        if not is_well_formed_event(event):
            return None

        if not self._auth(event):
            return None

        if not self._store.record_vote(event):
            return None

        return Vote.create(self.committee, self._identity, event)

    def handle_certificate(self, certificate: QuorumCertificate) -> bool:
        """
        Execute the certificate if it can run now. True if it was executed. A
        halted node executes nothing. That check is here and not in `_can_execute`,
        because the log replayed at a restart holds what ran before the halt.
        """
        if self._store.halted() or not self._can_execute(certificate):
            return False

        # On disk first: if this fails, the state has not changed.
        self._store.append_certificate(certificate)
        self._execute(certificate)
        return True

    def _can_execute(self, certificate: QuorumCertificate) -> bool:
        # Signatures last: they are the only expensive check, and the result does
        # not depend on the order because the checks have no side effects. The
        # check on the event comes first, because the others assume it.
        event = certificate.event
        return (
            is_well_formed_event(event)
            and self._is_fresh(event)
            and self._is_ready(event)
            and self._is_executable(event)
            and certificate.verify(self.committee)
        )

    def _is_fresh(self, event: Transfer) -> bool:
        return event.event_id() not in self._executed_ids

    def _is_ready(self, event: Transfer) -> bool:
        return set(event.parents) <= self._executed_ids

    def _is_executable(self, event: Transfer) -> bool:
        return (
            event.amount > 0
            and event.sender != event.receiver
            and StateDeriver._execution_failure(self.state, event) is None
        )

    def _execute(self, certificate: QuorumCertificate) -> None:
        StateDeriver._apply_one(self.state, certificate.event)
        self.log.append(certificate)
        self._executed_ids.add(certificate.event.event_id())


QUORUM_MESSAGE_TYPES = frozenset(
    {
        "VOTE_REQUEST",
        "VOTE",
        "CERTIFICATE",
        "CERTIFICATE_SYNC",
        "CERTIFICATE_SYNC_REQUEST",
    }
)

# Well under the 16 MiB of a frame. A node that needs more asks again.
SYNC_BATCH_BYTES = 4 * 1024 * 1024
# A sender left out is one the node asks everything about, which costs traffic and is
# still correct. The limit keeps the request itself within a frame.
SYNC_MAX_FRONTIER_SENDERS = 100_000


@dataclass(frozen=True)
class DriverOutput:
    """What to send. Sending comes after the call, with no lock held."""

    replies: tuple[dict, ...] = ()
    broadcasts: tuple[dict, ...] = ()


_NOTHING = DriverOutput()


class QuorumDriver:
    """
    The protocol around a replica: takes messages, returns messages to send. It
    uses no network and no Node.

    What it decides that the model has no counterpart for: which vote requests
    reach the replica, which votes count, and when the node halts. The retries of
    the buffer are what the model gets by delivering an input again.

    Each node aggregates only the votes for events submitted to it. If that node
    is lost, nobody completes the certificate until someone submits the event
    elsewhere. What it aggregated is in memory and lost at a restart, and the
    remedy is to submit again: a new vote gives the same signature.

    The buffer has no limit, because a limit would make the result depend on the
    order of arrival. Neither has the record of signed events: see the known limits
    on denial of service. Both are in memory, so a certificate still waiting is lost
    at a restart and has to be delivered again.

    Synchronization adds no transition: a certificate that arrives in a batch goes
    through the same path as one that arrives alone, and the model already allows any
    list of inputs for each node. A node asks with the next nonce of each sender. The
    position in the log would not do, because it differs from node to node. Nonces do,
    because a sender's nonces execute in sequence.

    Not thread-safe: the caller serializes the calls. A VoteStoreError propagates,
    and then nothing is to be sent.
    """

    def __init__(self, replica: QuorumReplica) -> None:
        self.replica = replica
        self.committee = replica.committee
        self.equivocations: dict[tuple[str, int], EquivocationProof] = {}
        self.signed_events: dict[str, SignedTransfer] = {}
        self._first_signed: dict[tuple[str, int], SignedTransfer] = {}
        self._aggregating: dict[bytes, tuple[Transfer, dict[int, Vote]]] = {}
        self._buffer: dict[str, QuorumCertificate] = {}
        # One certificate for each (sender, nonce), executed or waiting: a second
        # one for another event is the conflict that halts the node.
        self._known: dict[tuple[str, int], QuorumCertificate] = {
            (certificate.event.sender, certificate.event.nonce): certificate
            for certificate in replica.log
        }
        # The log by sender, in order of nonce, so that an answer does not read it all.
        self._log_by_sender: dict[str, list[QuorumCertificate]] = {}
        self._indexed = 0

    @property
    def halted(self) -> bool:
        return self.replica.halted()

    def handle_message(self, message: dict) -> DriverOutput:
        """
        Raises ValueError if the message is malformed, and the caller closes the
        connection. A message of the right form that is not valid only gets no
        answer: anyone can send one, and it must never stop the node.
        """
        message_type = message.get("type")

        if message_type == "VOTE_REQUEST":
            return self._handle_vote_request(decode_vote_request(message))

        if message_type == "VOTE":
            return self._handle_vote(*decode_vote(message))

        if message_type == "CERTIFICATE":
            return self._handle_certificate(decode_certificate(message))

        if message_type == "CERTIFICATE_SYNC":
            return self._handle_certificate_sync(decode_certificate_sync(message))

        if message_type == "CERTIFICATE_SYNC_REQUEST":
            return self._handle_sync_request(
                decode_certificate_sync_request(message)
            )

        raise ValueError("NOT A QUORUM MESSAGE")

    def sync_request(self) -> dict | None:
        """What to ask a peer for. None once halted: there is nothing more to do."""
        if self.halted:
            return None

        return encode_certificate_sync_request(self._frontier())

    def _frontier(self) -> dict[str, int]:
        self._refresh_log_index()
        state = self.replica.state
        frontier = {sender: state.nonce(sender) for sender in self._log_by_sender}

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

    def _handle_sync_request(self, frontier: dict[str, int]) -> DriverOutput:
        # Also after a halt: what was executed before it is still certified.
        self._refresh_log_index()
        batch = []
        size = 0

        for sender in sorted(self._log_by_sender):
            certificates = self._log_by_sender[sender]
            start = max(0, frontier.get(sender, 0) - certificates[0].event.nonce)

            for certificate in certificates[start:]:
                size += len(json.dumps(encode_certificate(certificate)))

                if batch and size > SYNC_BATCH_BYTES:
                    return DriverOutput(replies=(encode_certificate_sync(batch),))

                batch.append(certificate)

        if not batch:
            return _NOTHING

        return DriverOutput(replies=(encode_certificate_sync(batch),))

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

            # No honest node sends this. Stopping here means that a frame full of bad
            # certificates costs one check of a signature.
            if not certificate.verify(self.committee):
                return _NOTHING

            self._accept(certificate)
            learned = True

        request = self.sync_request() if learned else None

        # Only after learning something: this is what ends the exchange, and a peer
        # cannot make it last without new certificates.
        if request is None:
            return _NOTHING

        return DriverOutput(replies=(request,))

    def submit(self, signed: SignedTransfer) -> DriverOutput:
        """
        Start an event here: vote for it, then ask the others. If it already has a
        certificate, send that instead. If the vote is refused, nobody is asked,
        because an honest node does not ask for what it would not sign.
        """
        if not self._is_authorized(signed) or self.halted:
            return _NOTHING

        self._record_signed(signed)
        event = signed.transfer
        known = self._known.get((event.sender, event.nonce))

        if known is not None and known.event.canonical() == event.canonical():
            return DriverOutput(broadcasts=(encode_certificate(known),))

        vote = self.replica.handle_vote_request(event)

        if vote is None:
            return _NOTHING

        _, votes = self._aggregating.setdefault(event.canonical(), (event, {}))
        votes[vote.validator] = vote
        certificate = self._complete(event, votes)

        if certificate is not None:
            return DriverOutput(broadcasts=(encode_certificate(certificate),))

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
        if not self._is_authorized(signed):
            return _NOTHING

        # Before the replica, because a vote refused is when the proof appears.
        self._record_signed(signed)
        vote = self.replica.handle_vote_request(signed.transfer)

        if vote is None:
            return _NOTHING

        return DriverOutput(replies=(encode_vote(signed.transfer, vote),))

    def _handle_vote(self, event: Transfer, vote: Vote) -> DriverOutput:
        aggregating = self._aggregating.get(event.canonical())

        # A halt empties the aggregation, so nothing is found here after one.
        if aggregating is None:
            return _NOTHING

        event, votes = aggregating

        if not vote.verify(self.committee, event):
            return _NOTHING

        # By validator, so that the same one twice counts once.
        votes[vote.validator] = vote
        certificate = self._complete(event, votes)

        if certificate is None:
            return _NOTHING

        return DriverOutput(broadcasts=(encode_certificate(certificate),))

    def _complete(
        self,
        event: Transfer,
        votes: dict[int, Vote],
    ) -> QuorumCertificate | None:
        if len(votes) < self.committee.quorum:
            return None

        del self._aggregating[event.canonical()]
        certificate = QuorumCertificate(
            event,
            tuple(votes[validator] for validator in sorted(votes)),
        )
        self._accept(certificate)
        return certificate

    def _handle_certificate(self, certificate: QuorumCertificate) -> DriverOutput:
        if not self.halted and certificate.verify(self.committee):
            self._accept(certificate)

        return _NOTHING

    def _accept(self, certificate: QuorumCertificate) -> None:
        """The certificate is valid. Halt on a conflict, or try to execute it."""
        event = certificate.event
        key = (event.sender, event.nonce)
        known = self._known.get(key)

        if known is not None and known.event.canonical() != event.canonical():
            self.replica.record_halt(known, certificate)
            self._buffer.clear()
            self._aggregating.clear()
            return

        if known is None:
            self._known[key] = certificate
            self._buffer[event.event_id()] = certificate

        self._retry_buffer()

    def _retry_buffer(self) -> None:
        # In order of id and up to the fixed point, so that the result depends on
        # the set of certificates. A failed write leaves the certificate here, and
        # any later certificate tries it again.
        progress = True

        while progress:
            progress = False

            for event_id in sorted(self._buffer):
                if self.replica.handle_certificate(self._buffer[event_id]):
                    del self._buffer[event_id]
                    progress = True

    @staticmethod
    def _is_authorized(signed: SignedTransfer) -> bool:
        return (
            is_well_formed_event(signed.transfer)
            and signed.verify()
            and signed.identity_id == signed.transfer.sender
        )

    def _record_signed(self, signed: SignedTransfer) -> None:
        event = signed.transfer
        key = (event.sender, event.nonce)
        self.signed_events.setdefault(event.event_id(), signed)
        first = self._first_signed.setdefault(key, signed)

        if (
            first.transfer.canonical() != event.canonical()
            and key not in self.equivocations
        ):
            self.equivocations[key] = EquivocationProof(first, signed)


@dataclass(frozen=True)
class QuorumConfig:
    """What a node needs to run in quorum mode."""

    committee: Committee
    identity: Identity
    store_path: Path
    create: bool = False
    # Seconds between requests to each peer. None sends one only on connecting.
    sync_interval: float | None = 5.0


class QuorumRuntime:
    """
    Everything a node in quorum mode owns: the lock on the store, the store, the
    replica and the driver. Node holds this and adds the network.

    Only one process may use a store as a validator. Two processes would each
    believe its own aggregation and buffer, and a node stopped through one would
    still answer through the other. The lock is a flock on `<file>.lock`, which the
    kernel releases when the process dies, even by SIGKILL. It is not in the store
    because the store is allowed to be opened twice: the vote lock itself holds
    across processes. flock is not reliable on NFS.

    The replica gets no rule of its own for `auth`: the driver checks the signature
    and the sender before an event reaches it.
    """

    def __init__(self, config: QuorumConfig, initial_state: State) -> None:
        # Before anything on disk: a wrong genesis must leave no file behind.
        if initial_state.root() != config.committee.genesis_root:
            raise ValueError("INITIAL STATE IS NOT THE GENESIS OF THE COMMITTEE")

        self.closed = False
        self._lock_file = self._acquire_lock(Path(config.store_path))

        try:
            self._store = SqliteVoteStore(
                Path(config.store_path),
                config.committee,
                config.identity.public_key,
                create=config.create,
            )
        except BaseException:
            os.close(self._lock_file)
            raise

        try:
            self.replica = QuorumReplica(
                config.identity,
                initial_state,
                self._store,
                lambda _event: True,
            )
        except BaseException:
            self._store.close()
            os.close(self._lock_file)
            raise

        self.driver = QuorumDriver(self.replica)

    @staticmethod
    def _acquire_lock(path: Path) -> int:
        # Here and not at the top: node.py imports this module, and a node with
        # quorum=None must not need a module that only POSIX systems have.
        import fcntl

        try:
            descriptor = os.open(f"{path}.lock", os.O_RDWR | os.O_CREAT, 0o600)
        except OSError as error:
            raise VoteStoreError(f"CANNOT OPEN VOTE STORE LOCK: {error}") from error

        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            os.close(descriptor)
            raise VoteStoreError("VOTE STORE IS IN USE") from error

        return descriptor

    def close(self) -> None:
        if self.closed:
            return

        self.closed = True
        self._store.close()
        os.close(self._lock_file)
