"""
Quorum mode: docs/FORMAL-SPECIFICATION.md, section 13.1.

The model is in formal/lean/PSystem/Quorum.lean. The link between the two is
empirical, not a refinement proof.
"""

import json
import logging
import os
import sqlite3
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from core.attestation import (
    Committee,
    EpochChange,
    EpochClosure,
    EpochReport,
    Governance,
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
from network.remote_signer import SignerUnavailable
from network.message import (
    certificate_sync_request_epoch,
    decode_certificate,
    decode_certificate_sync,
    decode_certificate_sync_request,
    decode_closure_locked,
    decode_closure_vote,
    decode_closure_vote_request,
    decode_epoch_change,
    decode_epoch_closure,
    decode_epoch_report,
    decode_vote,
    decode_vote_request,
    encode_certificate,
    encode_certificate_sync,
    encode_certificate_sync_request,
    encode_closure_locked,
    encode_closure_vote,
    encode_closure_vote_request,
    encode_epoch_change,
    encode_epoch_closure,
    encode_epoch_report,
    encode_vote,
    encode_vote_request,
)


LOG = logging.getLogger("psystem.quorum")


class VoteStoreError(Exception):
    """
    The store cannot be trusted or could not record a write.

    Not a ValueError on purpose: a caller must not treat a failure to record as a
    malformed message. No signature may follow it.
    """


_SCHEMA_VERSION = "4"
_SCHEMA_VERSION_3 = "3"
_SCHEMA_VERSION_2 = "2"
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

_VOTES_TABLE = """
    CREATE TABLE votes (
        epoch INTEGER NOT NULL,
        sender TEXT NOT NULL,
        nonce TEXT NOT NULL,
        event_id TEXT NOT NULL,
        canonical TEXT NOT NULL,
        PRIMARY KEY (epoch, sender, nonce),
        UNIQUE (epoch, event_id)
    )
"""

# What schema 3 adds. A vote and the proof that its sender signed it are written together.
_EPOCH_TABLES = (
    """
    CREATE TABLE vote_evidence (
        epoch INTEGER NOT NULL,
        event_id TEXT NOT NULL,
        public_key TEXT NOT NULL,
        signature TEXT NOT NULL,
        PRIMARY KEY (epoch, event_id)
    )
    """,
    # An epoch with a row here votes for nothing more.
    "CREATE TABLE closed_epochs (epoch INTEGER PRIMARY KEY)",
    # This file came from a backup during this epoch: see `mark_restored`.
    "CREATE TABLE restored_epochs (epoch INTEGER PRIMARY KEY)",
    # The closure this validator voted for in an epoch: one, for good.
    """
    CREATE TABLE closure_votes (
        epoch INTEGER PRIMARY KEY,
        digest TEXT NOT NULL,
        closure TEXT
    )
    """,
    # The closure of `epoch`, which started `epoch + 1`.
    """
    CREATE TABLE closures (
        epoch INTEGER PRIMARY KEY,
        closure TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE locks (
        sender TEXT NOT NULL,
        nonce TEXT NOT NULL,
        canonical TEXT NOT NULL,
        PRIMARY KEY (sender, nonce, canonical)
    )
    """,
)

_SCHEMA = (
    """
    CREATE TABLE meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    # The nonce is text because Lean nonces are unbounded and an SQLite integer
    # has 64 bits. It is only compared for equality.
    _VOTES_TABLE,
    """
    CREATE TABLE certificates (
        position INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT NOT NULL UNIQUE,
        canonical TEXT NOT NULL,
        signatures TEXT NOT NULL,
        epoch INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE halt (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        first_canonical TEXT NOT NULL,
        first_signatures TEXT NOT NULL,
        second_canonical TEXT NOT NULL,
        second_signatures TEXT NOT NULL,
        first_epoch INTEGER NOT NULL DEFAULT 0,
        second_epoch INTEGER NOT NULL DEFAULT 0
    )
    """,
    *_EPOCH_TABLES,
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


def _certificate_from_row(
    canonical: str,
    signatures: str,
    epoch: int = 0,
) -> QuorumCertificate:
    return QuorumCertificate(
        _event_from_canonical(canonical),
        tuple(
            Vote(validator, bytes.fromhex(signature))
            for validator, signature in json.loads(signatures)
        ),
        epoch,
    )


def _is_halt_proof(
    committee_of: Callable[[QuorumCertificate], Committee],
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
        first.verify(committee_of(first))
        and second.verify(committee_of(second))
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
        governance: Governance | None = None,
        joining: bool = False,
    ) -> None:
        # `joining`: a node that enters in a later epoch, and votes only from then on.
        if committee.index_of(validator) is None and not joining:
            raise VoteStoreError("VALIDATOR IS NOT A COMMITTEE MEMBER")

        # The genesis of the chain, which the file belongs to, and the one in force.
        self.genesis_committee = committee
        self.committee = committee
        self.governance = governance
        self._chain: dict[int, Committee] = {committee.epoch: committee}
        self.validator = validator
        self._lock = threading.RLock()
        self._closed = False
        # True while a group holds the transaction: see `group`.
        self._grouped = False
        # For the metrics: writes to disk and the time they took.
        self.commits = 0
        self.commit_seconds = 0.0
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
                version = _SCHEMA_VERSION_2

            if version == _SCHEMA_VERSION_2:
                self._migrate_to_epochs()
            elif version == _SCHEMA_VERSION_3:
                # A closure voted under schema 3 has only its digest: nobody can take it over.
                self._connection.execute("ALTER TABLE closure_votes ADD COLUMN closure TEXT")
            elif version != _SCHEMA_VERSION:
                raise VoteStoreError("UNSUPPORTED VERSION OF THE VOTE STORE")

            if version != _SCHEMA_VERSION:
                self._connection.execute(
                    "UPDATE meta SET value = ? WHERE key = 'schema_version'",
                    (_SCHEMA_VERSION,),
                )
                self._commit()

            self._load_chain()
            self._check_halt_proof()
        finally:
            self._rollback_if_open()

    def _migrate_to_epochs(self) -> None:
        """
        To schema 3. The votes of schema 2 are the votes of epoch 0. They have no proof that
        the sender signed them, so such a validator cannot report: `close_epoch` refuses.
        """
        self._connection.execute("ALTER TABLE votes RENAME TO votes_v2")
        self._connection.execute(_VOTES_TABLE)
        self._connection.execute(
            """
            INSERT INTO votes (epoch, sender, nonce, event_id, canonical)
            SELECT 0, sender, nonce, event_id, canonical FROM votes_v2
            """
        )
        self._connection.execute("DROP TABLE votes_v2")
        self._connection.execute(
            "ALTER TABLE certificates ADD COLUMN epoch INTEGER NOT NULL DEFAULT 0"
        )
        self._connection.execute(
            "ALTER TABLE halt ADD COLUMN first_epoch INTEGER NOT NULL DEFAULT 0"
        )
        self._connection.execute(
            "ALTER TABLE halt ADD COLUMN second_epoch INTEGER NOT NULL DEFAULT 0"
        )

        for statement in _EPOCH_TABLES:
            self._connection.execute(statement)

    def _load_chain(self) -> None:
        # Each closure is checked again, from the committee before it. Whatever in the file
        # does not verify is an altered file, and the store does not open.
        for (closure_text,) in self._connection.execute(
            "SELECT closure FROM closures ORDER BY epoch"
        ).fetchall():
            if self.governance is None:
                raise VoteStoreError("THIS STORE HAS EPOCHS: GOVERNANCE IS REQUIRED")

            try:
                closure = decode_epoch_closure(
                    {"type": "EPOCH_CLOSURE", "closure": json.loads(closure_text)}
                )
            except (ValueError, TypeError, RecursionError) as error:
                raise VoteStoreError("CLOSURE IS UNREADABLE") from error

            if not closure.verify(self.governance, self.committee):
                raise VoteStoreError("CLOSURE DOES NOT VERIFY")

            self.committee = closure.change.next_committee(self.committee)
            self._chain[self.committee.epoch] = self.committee

    def reload_chain(self) -> None:
        """Back to what the file says, after a group that did not commit."""
        with self._lock:
            self.committee = self.genesis_committee
            self._chain = {self.committee.epoch: self.committee}

            try:
                self._load_chain()
            except sqlite3.Error as error:
                raise VoteStoreError(f"CANNOT READ CLOSURES: {error}") from error

    def committee_of(self, certificate: QuorumCertificate) -> Committee:
        """
        The committee that a certificate says it comes from. For an epoch this node does
        not know, the one in force: `verify` compares the epochs and answers False.
        """
        return self._chain.get(certificate.epoch, self.committee)

    def _read_halt_proof(self) -> tuple[QuorumCertificate, QuorumCertificate] | None:
        row = self._connection.execute(
            """
            SELECT first_canonical, first_signatures, first_epoch,
                   second_canonical, second_signatures, second_epoch
            FROM halt
            """
        ).fetchone()

        if row is None:
            return None

        return (
            _certificate_from_row(row[0], row[1], row[2]),
            _certificate_from_row(row[3], row[4], row[5]),
        )

    def _check_halt_proof(self) -> None:
        # A proof that does not verify means the file was altered. Neither ignoring
        # it nor believing it is safe, so the store does not open.
        try:
            proof = self._read_halt_proof()
        except (ValueError, KeyError, TypeError, RecursionError) as error:
            raise VoteStoreError("HALT PROOF IS UNREADABLE") from error

        if proof is not None and not _is_halt_proof(self.committee_of, *proof):
            raise VoteStoreError("HALT PROOF DOES NOT VERIFY")

    def _is_halted(self) -> bool:
        return (
            self._connection.execute("SELECT 1 FROM halt").fetchone() is not None
        )

    def _begin(self) -> None:
        # IMMEDIATE takes the write lock now, so the check and the write of a
        # vote are one step even for another process with the same file.
        if not self._grouped:
            self._connection.execute("BEGIN IMMEDIATE")

    def _timed_commit(self) -> None:
        started = time.perf_counter()
        self._connection.execute("COMMIT")
        self.commit_seconds += time.perf_counter() - started
        self.commits += 1

    def _commit(self) -> None:
        if not self._grouped:
            self._timed_commit()

    def _rollback_if_open(self) -> None:
        if not self._grouped and self._connection.in_transaction:
            self._connection.execute("ROLLBACK")

    @contextmanager
    def group(self):
        """
        Writes inside share one transaction and one fsync, and come out of it together or
        not at all. The caller must hold back every signature until this ends without an
        error, and must discard what it did in memory if it ends with one. Each write sees the
        writes before it, so one group decides what the same writes would decide one by one.
        """
        with self._lock:
            self._require_open()

            try:
                self._begin()
            except sqlite3.Error as error:
                raise VoteStoreError(f"GROUP NOT STARTED: {error}") from error

            self._grouped = True

            try:
                yield
                self._timed_commit()
            except sqlite3.Error as error:
                raise VoteStoreError(f"GROUP NOT RECORDED: {error}") from error
            finally:
                self._grouped = False
                self._rollback_if_open()

    def _require_open(self) -> None:
        if self._closed:
            raise VoteStoreError("VOTE STORE IS CLOSED")

    def record_vote(self, event: Transfer, signed: SignedTransfer | None = None) -> bool:
        """
        Apply the vote lock, `voteAllowed` and `lockAllows` in the model. False means that a
        different event holds the `(sender, nonce)` or the id in this epoch, or a lock from
        an earlier epoch, or that this epoch is closed, or that the node has halted, even
        for an event it already voted for. True means that this event is durably recorded,
        possibly by an earlier call.

        `signed` is the proof to report at the end of the epoch.

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

                epoch = self.committee.epoch

                if self._is_closed(epoch):
                    return False

                if self._is_locked_against(event, canonical):
                    return False

                existing = {
                    row[0]
                    for row in self._connection.execute(
                        """
                        SELECT canonical FROM votes
                        WHERE epoch = ? AND ((sender = ? AND nonce = ?) OR event_id = ?)
                        """,
                        (epoch, event.sender, str(event.nonce), event_id),
                    )
                }

                if existing - {canonical}:
                    return False

                if existing:
                    return True

                self._connection.execute(
                    """
                    INSERT INTO votes (epoch, sender, nonce, event_id, canonical)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (epoch, event.sender, str(event.nonce), event_id, canonical),
                )

                if signed is not None:
                    self._connection.execute(
                        """
                        INSERT INTO vote_evidence (epoch, event_id, public_key, signature)
                        VALUES (?, ?, ?, ?)
                        """,
                        (epoch, event_id, signed.public_key.hex(), signed.signature.hex()),
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
                    "SELECT canonical FROM votes WHERE epoch = ? ORDER BY rowid",
                    (self.committee.epoch,),
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
                    INSERT INTO certificates (event_id, canonical, signatures, epoch)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        event.event_id(),
                        event.canonical().decode(),
                        signatures,
                        certificate.epoch,
                    ),
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
                    "SELECT canonical, signatures, epoch FROM certificates ORDER BY position"
                ).fetchall()
            except sqlite3.Error as error:
                raise VoteStoreError(f"CANNOT READ CERTIFICATES: {error}") from error

        return [
            _certificate_from_row(canonical, signatures, epoch)
            for canonical, signatures, epoch in rows
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
        if not _is_halt_proof(self.committee_of, first, second):
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
                        first_canonical, first_signatures, first_epoch,
                        second_canonical, second_signatures, second_epoch
                    )
                    VALUES (1, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        low.event.canonical().decode(),
                        _encode_signatures(low),
                        low.epoch,
                        high.event.canonical().decode(),
                        _encode_signatures(high),
                        high.epoch,
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

    # Epochs: formal/lean/PSystem/QuorumEpochs.lean.

    def epoch_vote_count(self) -> int:
        with self._lock:
            self._require_open()

            try:
                return self._connection.execute(
                    "SELECT COUNT(*) FROM votes WHERE epoch = ?",
                    (self.committee.epoch,),
                ).fetchone()[0]
            except sqlite3.Error as error:
                raise VoteStoreError(f"CANNOT READ VOTES: {error}") from error

    def _is_closed(self, epoch: int) -> bool:
        return (
            self._connection.execute(
                "SELECT 1 FROM closed_epochs WHERE epoch = ?",
                (epoch,),
            ).fetchone()
            is not None
        )

    def is_locked_event(self, event: Transfer) -> bool:
        """This very event is among the locks of the closures so far."""
        with self._lock:
            self._require_open()

            try:
                return (
                    self._connection.execute(
                        "SELECT 1 FROM locks WHERE sender = ? AND nonce = ? AND canonical = ?",
                        (event.sender, str(event.nonce), event.canonical().decode()),
                    ).fetchone()
                    is not None
                )
            except sqlite3.Error as error:
                raise VoteStoreError(f"CANNOT READ LOCKS: {error}") from error

    def _is_locked_against(self, event: Transfer, canonical: str) -> bool:
        return any(
            row[0] != canonical
            for row in self._connection.execute(
                "SELECT canonical FROM locks WHERE sender = ? AND nonce = ?",
                (event.sender, str(event.nonce)),
            )
        )

    def close_epoch(self) -> list[SignedTransfer]:
        """
        Stop voting in this epoch, durably, and return all its votes. The two are one
        transaction, and after it no vote can be added: this is `report_holds_every_vote`.
        Calling it again returns the same votes, so a report can be sent again.
        """
        with self._lock:
            self._require_open()

            try:
                self._begin()
                epoch = self.committee.epoch

                if self._connection.execute(
                    "SELECT 1 FROM restored_epochs WHERE epoch = ?",
                    (epoch,),
                ).fetchone():
                    raise VoteStoreError("THIS FILE WAS RESTORED: IT REPORTS NOTHING IN THIS EPOCH")

                rows = self._connection.execute(
                    """
                    SELECT votes.canonical, vote_evidence.public_key, vote_evidence.signature
                    FROM votes LEFT JOIN vote_evidence
                    ON votes.epoch = vote_evidence.epoch
                    AND votes.event_id = vote_evidence.event_id
                    WHERE votes.epoch = ?
                    """,
                    (epoch,),
                ).fetchall()

                # A report without one of its votes could lose a certified event.
                if any(row[1] is None for row in rows):
                    raise VoteStoreError("A VOTE HAS NO PROOF OF ITS SENDER: CANNOT REPORT")

                self._connection.execute(
                    "INSERT OR IGNORE INTO closed_epochs (epoch) VALUES (?)",
                    (epoch,),
                )
                self._commit()
            except sqlite3.Error as error:
                raise VoteStoreError(f"EPOCH NOT CLOSED: {error}") from error
            finally:
                self._rollback_if_open()

        return [
            SignedTransfer(
                _event_from_canonical(canonical),
                bytes.fromhex(public_key),
                bytes.fromhex(signature),
            )
            for canonical, public_key, signature in rows
        ]

    def mark_restored(self) -> None:
        """
        This file came from a backup, so it may have lost votes this validator signed. Until
        the next epoch it votes for nothing and reports nothing: a report without those votes
        could lose a certified event. It executes certificates as usual. A validator that
        does this breaks no lock, because it signs nothing: `votes_stable_once_closed`.
        """
        with self._lock:
            self._require_open()

            try:
                self._begin()
                self._connection.execute(
                    "INSERT OR IGNORE INTO restored_epochs (epoch) VALUES (?)",
                    (self.committee.epoch,),
                )
                self._connection.execute(
                    "INSERT OR IGNORE INTO closed_epochs (epoch) VALUES (?)",
                    (self.committee.epoch,),
                )
                self._connection.execute(
                    "INSERT OR IGNORE INTO closure_votes (epoch, digest) VALUES (?, '')",
                    (self.committee.epoch,),
                )
                self._commit()
            except sqlite3.Error as error:
                raise VoteStoreError(f"NOT MARKED AS RESTORED: {error}") from error
            finally:
                self._rollback_if_open()

    def is_restored(self) -> bool:
        with self._lock:
            self._require_open()

            try:
                return (
                    self._connection.execute(
                        "SELECT 1 FROM restored_epochs WHERE epoch = ?",
                        (self.committee.epoch,),
                    ).fetchone()
                    is not None
                )
            except sqlite3.Error as error:
                raise VoteStoreError(f"CANNOT READ EPOCH: {error}") from error

    def epoch_is_closed(self) -> bool:
        with self._lock:
            self._require_open()

            try:
                return self._is_closed(self.committee.epoch)
            except sqlite3.Error as error:
                raise VoteStoreError(f"CANNOT READ EPOCH: {error}") from error

    def voted_closure(self) -> EpochClosure | None:
        """The candidate this validator voted for in this epoch, if it has it."""
        with self._lock:
            self._require_open()

            try:
                row = self._connection.execute(
                    "SELECT closure FROM closure_votes WHERE epoch = ?",
                    (self.committee.epoch,),
                ).fetchone()
            except sqlite3.Error as error:
                raise VoteStoreError(f"CANNOT READ CLOSURE VOTE: {error}") from error

        if row is None or row[0] is None:
            return None

        return decode_epoch_closure({"type": "EPOCH_CLOSURE", "closure": json.loads(row[0])})

    def record_closure_vote(self, closure: EpochClosure) -> bool:
        """
        The vote lock of the closure: one closure for each epoch, for good, or two nodes
        could hold different locks. True when this closure is durably the one, so a
        signature may follow. A closure that is refused here is not retried in this epoch.
        The whole closure goes on disk with the vote: it is what lets another node finish it.
        """
        digest = closure.digest
        text = json.dumps(encode_epoch_closure(closure)["closure"], separators=(",", ":"))

        with self._lock:
            self._require_open()

            try:
                self._begin()

                if self._is_halted():
                    # Halted, this node signs no closure.
                    return False

                epoch = self.committee.epoch
                row = self._connection.execute(
                    "SELECT digest FROM closure_votes WHERE epoch = ?",
                    (epoch,),
                ).fetchone()

                if row is not None:
                    return row[0] == digest

                self._connection.execute(
                    "INSERT INTO closure_votes (epoch, digest, closure) VALUES (?, ?, ?)",
                    (epoch, digest, text),
                )
                self._commit()
                return True
            except sqlite3.Error as error:
                raise VoteStoreError(f"CLOSURE VOTE NOT RECORDED: {error}") from error
            finally:
                self._rollback_if_open()

    def install_closure(self, closure: EpochClosure) -> None:
        """
        Enter the next epoch, with the locks of this closure added to the earlier ones. The
        caller has verified it. On disk first, and in one transaction.
        """
        current = self.committee
        following = closure.change.next_committee(current)
        locks = closure.locks()
        text = json.dumps(encode_epoch_closure(closure)["closure"], separators=(",", ":"))

        with self._lock:
            self._require_open()

            try:
                self._begin()

                if self._is_halted():
                    raise VoteStoreError("NODE HAS HALTED: NO NEW EPOCH")

                self._connection.execute(
                    "INSERT INTO closures (epoch, closure) VALUES (?, ?)",
                    (current.epoch, text),
                )
                self._connection.executemany(
                    """
                    INSERT OR IGNORE INTO locks (sender, nonce, canonical)
                    VALUES (?, ?, ?)
                    """,
                    [
                        (event.sender, str(event.nonce), event.canonical().decode())
                        for event in locks
                    ],
                )
                self._commit()
            except sqlite3.Error as error:
                raise VoteStoreError(f"CLOSURE NOT RECORDED: {error}") from error
            finally:
                self._rollback_if_open()

            self.committee = following
            self._chain[following.epoch] = following

    def closures(self, after_epoch: int = 0) -> list[EpochClosure]:
        """The closures from `after_epoch` on, in order."""
        with self._lock:
            self._require_open()

            try:
                rows = self._connection.execute(
                    "SELECT closure FROM closures WHERE epoch >= ? ORDER BY epoch",
                    (after_epoch,),
                ).fetchall()
            except sqlite3.Error as error:
                raise VoteStoreError(f"CANNOT READ CLOSURES: {error}") from error

        return [
            decode_epoch_closure({"type": "EPOCH_CLOSURE", "closure": json.loads(row[0])})
            for row in rows
        ]

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
        if identity.public_key != store.validator:
            raise ValueError("VOTE STORE BELONGS TO ANOTHER VALIDATOR")

        if initial_state.root() != store.committee.genesis_root:
            raise ValueError("INITIAL STATE IS NOT THE GENESIS OF THE COMMITTEE")

        self._identity = identity
        self._store = store
        self._auth = auth
        self.state = initial_state.copy()
        self.log: list[QuorumCertificate] = []
        self._executed_ids: set[str] = set()

        for certificate in store.certificates():
            if not self._can_replay(certificate):
                raise VoteStoreError("LOG OF CERTIFICATES DOES NOT REPLAY")
            self._execute(certificate)

    @property
    def committee(self) -> Committee:
        """The committee in force, which changes when a closure is installed."""
        return self._store.committee

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

        if not self._store.record_vote(event, signed):
            return None

        return self._signed_vote(event)

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

    def report_epoch(self, change_id: str) -> EpochReport | None:
        """
        Stop voting and report, durably in that order. None if this node has no vote in
        this epoch, because it is not a member of the committee.
        """
        if not self.is_member or self._store.halted() or self._store.is_restored():
            return None

        votes = self._store.close_epoch()

        try:
            return EpochReport.create(self.committee, self._identity, change_id, votes)
        except SignerUnavailable as error:
            LOG.error("signer gave no signature", extra={"reason": str(error)})
            return None

    def vote_for_closure(
        self,
        closure: EpochClosure,
        governance: Governance,
    ) -> Vote | None:
        """Sign one closure for this epoch, after the lock is on disk."""
        if not self.is_member or not self._store.record_closure_vote(closure):
            return None

        return self._signed_vote(closure.event(governance, self.committee))

    def voted_closure(self) -> EpochClosure | None:
        return self._store.voted_closure()

    def install_closure(self, closure: EpochClosure) -> None:
        self._store.install_closure(closure)

    def group(self):
        return self._store.group()

    def committee_of(self, certificate: QuorumCertificate) -> Committee:
        return self._store.committee_of(certificate)

    def closures(self, after_epoch: int = 0) -> list[EpochClosure]:
        return self._store.closures(after_epoch)

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

    def _can_run_now(self, event: Transfer) -> bool:
        # The check on the event comes first, because the others assume it.
        return (
            is_well_formed_event(event)
            and self._is_fresh(event)
            and self._is_ready(event)
            and self._is_executable(event)
        )

    def _can_execute(self, certificate: QuorumCertificate) -> bool:
        # Signatures last: they are the only expensive check, and the result does
        # not depend on the order because the checks have no side effects.
        return self._can_run_now(certificate.event) and self.certificate_is_valid(certificate)

    def _can_replay(self, certificate: QuorumCertificate) -> bool:
        return self._can_run_now(certificate.event) and self.certificate_was_valid(certificate)

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
        "EPOCH_CHANGE",
        "EPOCH_REPORT",
        "CLOSURE_VOTE_REQUEST",
        "CLOSURE_LOCKED",
        "CLOSURE_VOTE",
        "EPOCH_CLOSURE",
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
    # How long a closure in progress waits before what it needs is sent again.
    EPOCH_RETRY_SECONDS = 10.0

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

    def __init__(
        self,
        replica: QuorumReplica,
        governance: Governance | None = None,
        max_nonce_ahead: int | None = None,
        require_funds: bool = False,
        max_evidence: int | None = None,
        clock: Callable[[], float] = time.monotonic,
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
        # What this node proposed: the reports, then the votes on the closure.
        self._change: EpochChange | None = None
        self._reports: dict[int, EpochReport] = {}
        self._candidate: EpochClosure | None = None
        self._closure_votes: dict[int, Vote] = {}
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
                decode_certificate_sync_request(message),
                certificate_sync_request_epoch(message),
            )

        if message_type == "EPOCH_CHANGE":
            return self._handle_epoch_change(decode_epoch_change(message))

        if message_type == "EPOCH_REPORT":
            return self._handle_epoch_report(*decode_epoch_report(message))

        if message_type == "CLOSURE_VOTE_REQUEST":
            return self._handle_closure_vote_request(
                decode_closure_vote_request(message)
            )

        if message_type == "CLOSURE_LOCKED":
            return self._handle_closure_locked(decode_closure_locked(message))

        if message_type == "CLOSURE_VOTE":
            return self._handle_closure_vote(*decode_closure_vote(message))

        if message_type == "EPOCH_CLOSURE":
            return self._handle_epoch_closure(decode_epoch_closure(message))

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
        batch = []
        size = 0

        for sender in sorted(self._log_by_sender):
            certificates = self._log_by_sender[sender]
            start = max(0, frontier.get(sender, 0) - certificates[0].event.nonce)

            for certificate in certificates[start:]:
                size += len(json.dumps(encode_certificate(certificate)))

                if batch and size > SYNC_BATCH_BYTES:
                    return DriverOutput(
                        replies=(*closures, encode_certificate_sync(batch)),
                    )

                batch.append(certificate)

        if not batch:
            return DriverOutput(replies=closures)

        return DriverOutput(replies=(*closures, encode_certificate_sync(batch)))

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
            if not self.replica.certificate_is_valid(certificate):
                return _NOTHING

            self._accept(certificate)
            learned = True

        request = self.sync_request() if learned else None

        # Only after learning something: this is what ends the exchange, and a peer
        # cannot make it last without new certificates.
        if request is None:
            return _NOTHING

        return DriverOutput(replies=(request,))

    def propose_epoch_change(self, change: EpochChange) -> DriverOutput:
        """
        Order the end of this epoch, as a proposer. This node collects the reports and the
        votes on the closure. Only one proposer should act for an epoch: a closure that
        splits the votes of the committee ends with no closure at all, as an equivocating
        sender ends with no certificate.
        """
        if (
            self.governance is None
            or self.halted
            or not change.verify(self.governance, self.committee)
        ):
            return _NOTHING

        self._change = change
        self._reports = {}
        self._candidate = None
        self._closure_votes = {}
        self._epoch_activity = self._clock()
        broadcasts = [encode_epoch_change(change)]
        report = self.replica.report_epoch(change.change_id)

        if report is not None:
            self._reports[report.validator] = report

        # A closure this node already voted for can only be finished, not replaced.
        voted = self._voted_closure_for(change)

        if voted is not None:
            broadcasts.extend(self._adopt(voted).broadcasts)
        else:
            broadcasts.extend(self._closure_if_reported().broadcasts)

        return DriverOutput(broadcasts=tuple(broadcasts))

    def _voted_closure_for(self, change: EpochChange) -> EpochClosure | None:
        voted = self.replica.voted_closure()

        if voted is None or voted.change.change_id != change.change_id:
            return None

        return voted

    def _adopt(self, closure: EpochClosure) -> DriverOutput:
        """Work for a closure that members already voted for, in place of any other."""
        self._candidate = closure
        self._closure_votes = {}
        self._epoch_activity = self._clock()
        vote = self.replica.vote_for_closure(closure, self.governance)

        if vote is not None:
            self._closure_votes[vote.validator] = vote

        return DriverOutput(broadcasts=(encode_closure_vote_request(closure),))

    def retry(self) -> DriverOutput:
        """
        Call it now and then. A closure in progress sends again what may have been lost, and
        a member that voted for a closure and never saw it finish works for it itself, since
        whoever proposed it may be dead. Several nodes doing this for one closure is harmless:
        they ask for the same votes. So this adds no way to split the votes.
        """
        if (
            self.governance is None
            or self.halted
            or self._clock() - self._epoch_activity < self.EPOCH_RETRY_SECONDS
        ):
            return _NOTHING

        if self._candidate is None and self._change is None:
            voted = self.replica.voted_closure()

            if voted is None or not voted.is_valid_candidate(self.governance, self.committee):
                return _NOTHING

            self._change = voted.change
            return self._adopt(voted)

        self._epoch_activity = self._clock()

        if self._candidate is not None:
            return DriverOutput(broadcasts=(encode_closure_vote_request(self._candidate),))

        return DriverOutput(broadcasts=(encode_epoch_change(self._change),))

    def _handle_epoch_change(self, change: EpochChange) -> DriverOutput:
        if (
            self.governance is None
            or self.halted
            or not change.verify(self.governance, self.committee)
        ):
            return _NOTHING

        replies = []
        voted = self._voted_closure_for(change)

        # First, so that a proposer knows of it before it has enough reports to make another.
        if voted is not None:
            replies.append(encode_closure_locked(voted))

        report = self.replica.report_epoch(change.change_id)

        if report is not None:
            replies.append(encode_epoch_report(change.change_id, report))

        return DriverOutput(replies=tuple(replies))

    def _handle_epoch_report(self, change_id: str, report: EpochReport) -> DriverOutput:
        if (
            self._change is None
            or self._candidate is not None
            or change_id != self._change.change_id
            or not report.verify(self.committee, change_id)
        ):
            return _NOTHING

        self._reports[report.validator] = report
        self._epoch_activity = self._clock()
        return self._closure_if_reported()

    def _closure_if_reported(self) -> DriverOutput:
        if self._candidate is not None or len(self._reports) < self.committee.quorum:
            return _NOTHING

        self._candidate = EpochClosure(
            self._change,
            tuple(self._reports[validator] for validator in sorted(self._reports)),
        )
        vote = self.replica.vote_for_closure(self._candidate, self.governance)

        if vote is not None:
            self._closure_votes[vote.validator] = vote

        return DriverOutput(broadcasts=(encode_closure_vote_request(self._candidate),))

    def _handle_closure_vote_request(self, closure: EpochClosure) -> DriverOutput:
        if (
            self.governance is None
            or self.halted
            or not closure.is_valid_candidate(self.governance, self.committee)
        ):
            return _NOTHING

        vote = self.replica.vote_for_closure(closure, self.governance)

        if vote is None:
            voted = self.replica.voted_closure()

            if voted is None:
                return _NOTHING

            return DriverOutput(replies=(encode_closure_locked(voted),))

        self._epoch_activity = self._clock()
        return DriverOutput(replies=(encode_closure_vote(closure.digest, vote),))

    def _handle_closure_locked(self, closure: EpochClosure) -> DriverOutput:
        """
        A member already voted for this closure, and cannot vote for another. Only who is
        working on that order of governance cares. A faulty member can send any valid
        candidate here, and that can only waste the votes, as a second proposer can.
        """
        if (
            self.governance is None
            or self.halted
            or self._change is None
            or closure.change.change_id != self._change.change_id
            or (self._candidate is not None and self._candidate.digest == closure.digest)
            or not closure.is_valid_candidate(self.governance, self.committee)
        ):
            return _NOTHING

        return self._adopt(closure)

    def _handle_closure_vote(self, digest: str, vote: Vote) -> DriverOutput:
        candidate = self._candidate

        if (
            candidate is None
            or digest != candidate.digest
            or not vote.verify(
                self.committee,
                candidate.event(self.governance, self.committee),
            )
        ):
            return _NOTHING

        self._closure_votes[vote.validator] = vote

        if len(self._closure_votes) < self.committee.quorum:
            return _NOTHING

        closure = EpochClosure(
            candidate.change,
            candidate.reports,
            tuple(self._closure_votes[v] for v in sorted(self._closure_votes)),
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
            or not closure.verify(self.governance, self.committee)
        ):
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
                "locks": len(closure.locks()),
            },
        )
        # Votes collected so far were signed for the committee that has ended.
        self._aggregating.clear()
        self._change = None
        self._reports = {}
        self._candidate = None
        self._closure_votes = {}
        self._epoch_activity = self._clock()
        self._retry_buffer()

    def submit(self, signed: SignedTransfer) -> DriverOutput:
        """
        Start an event here: vote for it, then ask the others. If it already has a
        certificate, send that instead. If the vote is refused, nobody is asked,
        because an honest node does not ask for what it would not sign.
        """
        if not self._is_authorized(signed) or self.halted:
            return _NOTHING

        if not self._is_admitted(signed.transfer):
            return _NOTHING

        self._record_signed(signed)
        event = signed.transfer
        known = self._known.get((event.sender, event.nonce))

        if known is not None and known.event.canonical() == event.canonical():
            return DriverOutput(broadcasts=(encode_certificate(known),))

        vote = self.replica.handle_vote_request(event, signed)

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

        if not self._is_admitted(signed.transfer):
            return _NOTHING

        # Before the replica, because a vote refused is when the proof appears.
        self._record_signed(signed)
        vote = self.replica.handle_vote_request(signed.transfer, signed)

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
            self.committee.epoch,
        )
        self._accept(certificate)
        return certificate

    def _handle_certificate(self, certificate: QuorumCertificate) -> DriverOutput:
        if not self.halted and self.replica.certificate_is_valid(certificate):
            self._accept(certificate)

        return _NOTHING

    def _accept(self, certificate: QuorumCertificate) -> None:
        """The certificate is valid. Halt on a conflict, or try to execute it."""
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
                return

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
    # Who may order the end of an epoch. None: this committee never changes.
    governance: Governance | None = None
    # This node is not in `committee`, the first of the chain, and enters later.
    joining: bool = False
    # What an honest node may refuse before voting: see `QuorumDriver`. Off by default, like
    # the model. The service turns them on.
    max_nonce_ahead: int | None = None
    require_funds: bool = False
    max_evidence: int | None = None


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
        self._identity = config.identity
        self._initial_state = initial_state
        self._config = config
        self._lock_file = self._acquire_lock(Path(config.store_path))

        try:
            self._store = SqliteVoteStore(
                Path(config.store_path),
                config.committee,
                config.identity.public_key,
                create=config.create,
                governance=config.governance,
                joining=config.joining,
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

        self.driver = self._new_driver()

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

    def handle_group(self, messages: list[dict]) -> tuple[DriverOutput, Exception | None]:
        """
        Several messages, one transaction. Equal to handling them one by one, except that
        all the output comes after the commit. A malformed message stops the group: what
        came before it counts, and the caller gets the error to close the connection, as
        it would have.

        If the commit fails nothing came out of it, and what the driver and the replica did
        in memory did not happen either, so both are rebuilt from the disk. The error goes up,
        and nothing is sent. Evidence in memory goes too: it is not part of the protocol.
        """
        replies = []
        broadcasts = []
        error = None

        with self._group_or_rebuild():
            for message in messages:
                try:
                    output = self.driver.handle_message(message)
                except (ValueError, KeyError, TypeError, RecursionError) as malformed:
                    error = malformed
                    break

                replies.extend(output.replies)
                broadcasts.extend(output.broadcasts)

        return DriverOutput(tuple(replies), tuple(broadcasts)), error

    @contextmanager
    def _group_or_rebuild(self):
        try:
            with self.replica.group():
                yield
        except VoteStoreError:
            self._rebuild()
            raise

    def _new_driver(self) -> QuorumDriver:
        return QuorumDriver(
            self.replica,
            self._config.governance,
            self._config.max_nonce_ahead,
            self._config.require_funds,
            self._config.max_evidence,
        )

    def submit_group(self, events: list[SignedTransfer]) -> DriverOutput:
        """Start several events here, with one write for all the votes of this node."""
        replies = []
        broadcasts = []

        with self._group_or_rebuild():
            for signed in events:
                output = self.driver.submit(signed)
                replies.extend(output.replies)
                broadcasts.extend(output.broadcasts)

        return DriverOutput(tuple(replies), tuple(broadcasts))

    def _rebuild(self) -> None:
        self._store.reload_chain()
        self.replica = QuorumReplica(
            self._identity,
            self._initial_state,
            self._store,
            lambda _event: True,
        )
        self.driver = self._new_driver()

    def close(self) -> None:
        if self.closed:
            return

        self.closed = True
        self._store.close()
        os.close(self._lock_file)
