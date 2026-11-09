"""
Quorum mode: docs/FORMAL-SPECIFICATION.md, section 13.1.

The model is in formal/lean/PSystem/Quorum.lean. The link between the two is
empirical, not a refinement proof.
"""

import heapq
import json
import logging
import os
import sqlite3
import threading
import time
from bisect import bisect_left
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path

from core.attestation import (
    ClosureHeader,
    Committee,
    EpochChange,
    EpochClosure,
    EpochReport,
    Governance,
    QuorumCertificate,
    Snapshot,
    SnapshotAttestation,
    Vote,
    is_well_formed_event,
)
from core.derive import StateDeriver
from core.attestation import is_authorized_transfer, stays_in_one_asset
from core.event import Transfer
from core.equivocation import EquivocationProof
from core.signed_event import SignedTransfer
from core.state import State
from crypto.identity import Identity
from network.remote_signer import SignerUnavailable, make_private
from network.message import (
    certificate_sync_request_epoch,
    decode_certificate,
    decode_certificate_sync,
    decode_certificate_sync_request,
    decode_epoch_change,
    decode_epoch_closure,
    decode_epoch_report,
    decode_snapshot,
    decode_snapshot_body,
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
    encode_snapshot_body,
    encode_snapshot_request,
    encode_snapshot_vote,
    encode_vote,
    encode_vote_request,
)


LOG = logging.getLogger("psystem.quorum")


def is_executable_event(event: Transfer) -> bool:
    """The part of executability that no later state can change."""
    return event.amount > 0 and event.sender != event.receiver


class VoteStoreError(Exception):
    """
    The store cannot be trusted or could not record a write.

    Not a ValueError on purpose: a caller must not treat a failure to record as a
    malformed message. No signature may follow it.
    """


_SCHEMA_VERSION = "7"
_SCHEMA_VERSION_6 = "6"
_SCHEMA_VERSION_5 = "5"
_SCHEMA_VERSION_4 = "4"
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

# What schema 5 adds. One snapshot, the last. The floors are what this validator no longer votes under,
# and are written only when it has pruned locks: `no_double_spend_views` needs the two together.
#
# The order this validator reported for in an epoch: one, for good. It is what `order_unique` is about.
_SNAPSHOT_TABLES = (
    """
    CREATE TABLE report_locks (
        epoch INTEGER PRIMARY KEY,
        change_id TEXT NOT NULL,
        change TEXT NOT NULL
    )
    """,
    "CREATE TABLE snapshot (id INTEGER PRIMARY KEY CHECK (id = 1), body TEXT NOT NULL)",
    "CREATE TABLE floors (sender TEXT PRIMARY KEY, nonce TEXT NOT NULL)",
)

# What schema 6 adds: the events this node took and asks votes for. The event and the proof that its
# sender signed it are in `votes` and `vote_evidence`, so that a row costs little, and it is written
# with the vote: a client that got its answer can count on this surviving, and it costs no other fsync.
_GATHERING_TABLE = """
    CREATE TABLE gathering (
        event_id TEXT PRIMARY KEY,
        epoch INTEGER NOT NULL
    )
"""

# What schema 7 adds: the signature of the sender of each lock, so that a snapshot can pass the lock on
# and whoever takes it can check it. A lock from a file before schema 7 that no closure on file signs
# keeps NULL here: it still refuses votes, and this validator signs no snapshot it would have to carry.
_SIGNED_LOCK_COLUMNS = (
    "ALTER TABLE locks ADD COLUMN public_key TEXT",
    "ALTER TABLE locks ADD COLUMN signature TEXT",
)

# In a file before schema 5. A closure no longer takes votes.
_OLD_CLOSURE_VOTES = """
    CREATE TABLE closure_votes (
        epoch INTEGER PRIMARY KEY,
        digest TEXT NOT NULL,
        closure TEXT
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
    *_SNAPSHOT_TABLES,
    _GATHERING_TABLE,
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


def _change_text(change: EpochChange) -> str:
    return json.dumps(encode_epoch_change(change)["change"], separators=(",", ":"))


def _header_text(header: ClosureHeader) -> str:
    return json.dumps(
        {
            "change": encode_epoch_change(header.change)["change"],
            "header": [
                [validator, digest.hex(), signature.hex()]
                for validator, digest, signature in header.reports
            ],
        },
        separators=(",", ":"),
    )


def _closure_from_text(text: str) -> EpochClosure | ClosureHeader:
    data = json.loads(text)

    if type(data) is dict and "header" in data:
        return ClosureHeader(
            decode_epoch_change({"type": "EPOCH_CHANGE", "change": data["change"]}),
            tuple(
                (validator, bytes.fromhex(digest), bytes.fromhex(signature))
                for validator, digest, signature in data["header"]
            ),
        )

    return decode_epoch_closure({"type": "EPOCH_CLOSURE", "closure": data})


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
            make_private(Path(path), create=create)
            self._connection = sqlite3.connect(
                f"{Path(path).resolve().as_uri()}?mode={mode}",
                uri=True,
                isolation_level=None,
                check_same_thread=False,
                timeout=30.0,
            )
        except (sqlite3.Error, OSError) as error:
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

                for statement in (*_SCHEMA, *_SIGNED_LOCK_COLUMNS):
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
                # A closure voted under schema 3 has only its digest.
                self._connection.execute("ALTER TABLE closure_votes ADD COLUMN closure TEXT")
            elif version not in (_SCHEMA_VERSION, _SCHEMA_VERSION_6, _SCHEMA_VERSION_5, _SCHEMA_VERSION_4):
                raise VoteStoreError("UNSUPPORTED VERSION OF THE VOTE STORE")

            if version not in (_SCHEMA_VERSION, _SCHEMA_VERSION_6, _SCHEMA_VERSION_5):
                for statement in _SNAPSHOT_TABLES:
                    self._connection.execute(statement)

                self._drop_closure_votes()

            if version != _SCHEMA_VERSION:
                if version != _SCHEMA_VERSION_6:
                    self._connection.execute(_GATHERING_TABLE)

                columns = {row[1] for row in self._connection.execute("PRAGMA table_info(locks)")}

                if "signature" not in columns:
                    for statement in _SIGNED_LOCK_COLUMNS:
                        self._connection.execute(statement)

                self._sign_locks_from_closures()
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

        self._connection.execute(_OLD_CLOSURE_VOTES)

    def _drop_closure_votes(self) -> None:
        """
        To schema 5. A closure voted for names the order this validator reported for, so that is
        its lock. An epoch closed with only a digest left says nothing of the order, and
        `close_epoch` then gives no more reports. Closures on file lose their votes.
        """
        for epoch, text in self._connection.execute(
            "SELECT epoch, closure FROM closure_votes WHERE closure IS NOT NULL"
        ).fetchall():
            change = decode_epoch_change(
                {"type": "EPOCH_CHANGE", "change": json.loads(text)["change"]}
            )
            self._connection.execute(
                "INSERT INTO report_locks (epoch, change_id, change) VALUES (?, ?, ?)",
                (epoch, change.change_id, _change_text(change)),
            )

        self._connection.execute("DROP TABLE closure_votes")

        for epoch, text in self._connection.execute(
            "SELECT epoch, closure FROM closures"
        ).fetchall():
            body = json.loads(text)
            body.pop("votes", None)
            self._connection.execute(
                "UPDATE closures SET closure = ? WHERE epoch = ?",
                (json.dumps(body, separators=(",", ":")), epoch),
            )

    def _sign_locks_from_closures(self) -> None:
        """
        To schema 7. A lock from a closure on file gets the signature its report carried. One from a
        snapshot, or from a closure kept only as a header, has none to get.
        """
        for (text,) in self._connection.execute("SELECT closure FROM closures").fetchall():
            try:
                closure = _closure_from_text(text)
            except (ValueError, KeyError, TypeError, RecursionError) as error:
                raise VoteStoreError("CLOSURE IS UNREADABLE") from error

            if not isinstance(closure, EpochClosure):
                continue

            for report in closure.reports:
                for signed in report.votes:
                    if not is_authorized_transfer(signed):
                        continue

                    event = signed.transfer
                    self._connection.execute(
                        """
                        UPDATE locks SET public_key = ?, signature = ?
                        WHERE sender = ? AND nonce = ? AND canonical = ? AND signature IS NULL
                        """,
                        (
                            signed.public_key.hex(),
                            signed.signature.hex(),
                            event.sender,
                            str(event.nonce),
                            event.canonical().decode(),
                        ),
                    )

    def _load_chain(self) -> None:
        # Each closure is checked again, from the committee before it. Whatever in the file
        # does not verify is an altered file, and the store does not open.
        for (closure_text,) in self._connection.execute(
            "SELECT closure FROM closures ORDER BY epoch"
        ).fetchall():
            if self.governance is None:
                raise VoteStoreError("THIS STORE HAS EPOCHS: GOVERNANCE IS REQUIRED")

            try:
                closure = _closure_from_text(closure_text)
            except (ValueError, KeyError, TypeError, RecursionError) as error:
                raise VoteStoreError("CLOSURE IS UNREADABLE") from error

            if not closure.verify(self.governance, self.committee):
                raise VoteStoreError("CLOSURE DOES NOT VERIFY")

            self.committee = closure.change.next_committee(self.committee)
            self._chain[self.committee.epoch] = self.committee

    def committee_at(self, epoch: int) -> Committee | None:
        return self._chain.get(epoch)

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

    def record_vote(
        self,
        event: Transfer,
        signed: SignedTransfer | None = None,
        gathering: bool = False,
    ) -> bool:
        """
        Apply the vote lock, `voteAllowed` and `lockAllows` in the model. False means that a
        different event holds the `(sender, nonce)` or the id in this epoch, or a lock from
        an earlier epoch, or that this epoch is closed, or that the node has halted, even
        for an event it already voted for. True means that this event is durably recorded,
        possibly by an earlier call.

        `signed` is the proof to report at the end of the epoch. `gathering`: this node took the event
        and asks votes for it, and that is written with the vote: see `gathering`.

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

                # The other half of a pruned lock, and the two are one rule.
                if self._is_below_floor(event):
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
                    if gathering:
                        self._record_gathering(epoch, event_id)
                        self._commit()

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

                if gathering:
                    self._record_gathering(epoch, event_id)

                self._commit()
                return True
            except sqlite3.Error as error:
                raise VoteStoreError(f"VOTE NOT RECORDED: {error}") from error
            finally:
                self._rollback_if_open()

    def _record_gathering(self, epoch: int, event_id: str) -> None:
        self._connection.execute(
            "INSERT OR IGNORE INTO gathering (event_id, epoch) VALUES (?, ?)",
            (event_id, epoch),
        )

    def gathering(self) -> list[SignedTransfer]:
        """
        The events this node took in this epoch with no certificate on file, oldest first. A vote with
        no proof of its sender cannot be asked for again, and it comes only from an old file.
        """
        with self._lock:
            self._require_open()

            try:
                rows = self._connection.execute(
                    """
                    SELECT votes.canonical, vote_evidence.public_key, vote_evidence.signature
                    FROM gathering
                    JOIN votes ON votes.epoch = gathering.epoch AND votes.event_id = gathering.event_id
                    JOIN vote_evidence
                    ON vote_evidence.epoch = gathering.epoch AND vote_evidence.event_id = gathering.event_id
                    WHERE gathering.epoch = ?
                    ORDER BY gathering.rowid
                    """,
                    (self.committee.epoch,),
                ).fetchall()
            except sqlite3.Error as error:
                raise VoteStoreError(f"CANNOT READ WHAT IS GATHERING: {error}") from error

        return [
            SignedTransfer(
                _event_from_canonical(canonical),
                bytes.fromhex(public_key),
                bytes.fromhex(signature),
            )
            for canonical, public_key, signature in rows
        ]

    def forget_gathering(self, event_ids: list[str]) -> None:
        with self._lock:
            self._require_open()

            try:
                self._begin()
                self._connection.executemany(
                    "DELETE FROM gathering WHERE event_id = ?",
                    [(event_id,) for event_id in event_ids],
                )
                self._commit()
            except sqlite3.Error as error:
                raise VoteStoreError(f"CANNOT FORGET WHAT WAS GATHERING: {error}") from error
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
                self._connection.execute(
                    "DELETE FROM gathering WHERE event_id = ?",
                    (event.event_id(),),
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

    def _is_below_floor(self, event: Transfer) -> bool:
        row = self._connection.execute(
            "SELECT nonce FROM floors WHERE sender = ?",
            (event.sender,),
        ).fetchone()
        return row is not None and event.nonce < int(row[0])

    # Snapshots: formal/lean/PSystem/QuorumSnapshot.lean.

    def snapshot(self) -> Snapshot | None:
        """The last snapshot this node took. The caller checks it: the file may be altered."""
        with self._lock:
            self._require_open()

            try:
                row = self._connection.execute("SELECT body FROM snapshot").fetchone()
            except sqlite3.Error as error:
                raise VoteStoreError(f"CANNOT READ SNAPSHOT: {error}") from error

        if row is None:
            return None

        try:
            return decode_snapshot_body(json.loads(row[0]), legacy=True)
        except (ValueError, KeyError, TypeError, RecursionError) as error:
            raise VoteStoreError("SNAPSHOT IS UNREADABLE") from error

    def record_snapshot(self, snapshot: Snapshot) -> None:
        """Keep it, with the locks of its signers. More locks can only refuse more votes."""
        text = json.dumps(encode_snapshot_body(snapshot), separators=(",", ":"))

        with self._lock:
            self._require_open()

            try:
                self._begin()
                self._connection.execute(
                    "INSERT OR REPLACE INTO snapshot (id, body) VALUES (1, ?)",
                    (text,),
                )
                self._add_locks(snapshot.locks())
                self._commit()
            except sqlite3.Error as error:
                raise VoteStoreError(f"SNAPSHOT NOT RECORDED: {error}") from error
            finally:
                self._rollback_if_open()

    def _add_locks(self, locks: tuple[SignedTransfer, ...] | list[SignedTransfer]) -> None:
        """Each lock with the signature of its sender. A lock already held without one gets it."""
        self._connection.executemany(
            """
            INSERT INTO locks (sender, nonce, canonical, public_key, signature) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (sender, nonce, canonical) DO UPDATE
            SET public_key = excluded.public_key, signature = excluded.signature
            WHERE locks.signature IS NULL
            """,
            [
                (
                    signed.transfer.sender,
                    str(signed.transfer.nonce),
                    signed.transfer.canonical().decode(),
                    signed.public_key.hex(),
                    signed.signature.hex(),
                )
                for signed in locks
            ],
        )

    def locks_over(self, nonces: dict[str, int]) -> list[SignedTransfer] | None:
        """
        The locks this validator holds that a floor at `nonces` keeps, each signed by its sender. None
        if one of them has no signature, from a file before schema 7: a snapshot without it could lose
        a lock (`union_locks_cover`), so this validator signs none until a floor passes it.
        """
        with self._lock:
            self._require_open()

            try:
                rows = self._connection.execute(
                    "SELECT sender, nonce, canonical, public_key, signature FROM locks ORDER BY canonical"
                ).fetchall()
            except sqlite3.Error as error:
                raise VoteStoreError(f"CANNOT READ LOCKS: {error}") from error

        kept = [row for row in rows if int(row[1]) >= nonces.get(row[0], 0)]

        if any(row[4] is None for row in kept):
            return None

        return [
            SignedTransfer(
                _event_from_canonical(canonical),
                bytes.fromhex(public_key),
                bytes.fromhex(signature),
            )
            for _sender, _nonce, canonical, public_key, signature in kept
        ]

    def forget_certificates(self, event_ids: list[str]) -> None:
        """Pruning. The caller holds a verified snapshot that covers them."""
        with self._lock:
            self._require_open()

            try:
                self._begin()
                self._connection.executemany(
                    "DELETE FROM certificates WHERE event_id = ?",
                    [(event_id,) for event_id in event_ids],
                )
                self._commit()
            except sqlite3.Error as error:
                raise VoteStoreError(f"CERTIFICATES NOT PRUNED: {error}") from error
            finally:
                self._rollback_if_open()

    def apply_floor(self, snapshot: Snapshot) -> None:
        """
        From now on no vote under this floor, and the locks under it go, in one transaction. Only at
        the start of an epoch, where the model has it, and never one without the other:
        `prune_without_floor_lets_conflict_through`. A floor that is too high only refuses more
        votes. Votes and report locks of ended epochs go too: nothing reads them.
        """
        epoch = self.committee.epoch

        with self._lock:
            self._require_open()

            try:
                self._begin()
                self._connection.executemany(
                    "INSERT OR REPLACE INTO floors (sender, nonce) VALUES (?, ?)",
                    [(sender, str(nonce)) for sender, nonce in snapshot.state.nonces.items()],
                )
                stale = [
                    (sender, nonce)
                    for sender, nonce in self._connection.execute(
                        "SELECT DISTINCT sender, nonce FROM locks"
                    )
                    if int(nonce) < snapshot.floor(sender)
                ]
                self._connection.executemany(
                    "DELETE FROM locks WHERE sender = ? AND nonce = ?",
                    stale,
                )

                for table in ("votes", "vote_evidence", "report_locks"):
                    self._connection.execute(f"DELETE FROM {table} WHERE epoch < ?", (epoch,))

                # The last closure stays whole, for a peer one epoch behind. The older ones keep only
                # what proves the chain: what they locked is in the table above.
                for old_epoch, text in self._connection.execute(
                    "SELECT epoch, closure FROM closures WHERE epoch < ?",
                    (epoch - 1,),
                ).fetchall():
                    old = _closure_from_text(text)

                    if isinstance(old, EpochClosure):
                        self._connection.execute(
                            "UPDATE closures SET closure = ? WHERE epoch = ?",
                            (_header_text(ClosureHeader.of(old)), old_epoch),
                        )

                self._commit()
            except sqlite3.Error as error:
                raise VoteStoreError(f"FLOOR NOT RECORDED: {error}") from error
            finally:
                self._rollback_if_open()

    def close_epoch(self, change: EpochChange) -> list[SignedTransfer] | None:
        """
        Stop voting in this epoch, durably, and return all its votes. The two are one
        transaction, and after it no vote can be added: this is `report_holds_every_vote`.
        Calling it again returns the same votes, so a report can be sent again.

        None for an order other than the first: one order for each epoch, for good, which is what
        `order_unique` needs. Also for an epoch already closed with no order on file, from a file
        older than this rule: that validator may have reported for any.
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

                lock = self._connection.execute(
                    "SELECT change_id FROM report_locks WHERE epoch = ?",
                    (epoch,),
                ).fetchone()

                if lock is None and self._is_closed(epoch):
                    return None

                if lock is not None and lock[0] != change.change_id:
                    return None

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
                self._connection.execute(
                    "INSERT OR IGNORE INTO report_locks (epoch, change_id, change) VALUES (?, ?, ?)",
                    (epoch, change.change_id, _change_text(change)),
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

    def reported_change(self) -> EpochChange | None:
        """The order this validator reported for in this epoch, if any."""
        with self._lock:
            self._require_open()

            try:
                row = self._connection.execute(
                    "SELECT change FROM report_locks WHERE epoch = ?",
                    (self.committee.epoch,),
                ).fetchone()
            except sqlite3.Error as error:
                raise VoteStoreError(f"CANNOT READ REPORT LOCK: {error}") from error

        if row is None:
            return None

        return decode_epoch_change({"type": "EPOCH_CHANGE", "change": json.loads(row[0])})

    def install_closure(self, closure: EpochClosure) -> None:
        """
        Enter the next epoch, with the locks of this closure added to the earlier ones. The
        caller has verified it. On disk first, and in one transaction.
        """
        current = self.committee
        following = closure.change.next_committee(current)
        locks = closure.signed_locks(current)
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
                self._add_locks(locks)
                # Votes signed for the committee that ended, which the driver forgets as well.
                self._connection.execute(
                    "DELETE FROM gathering WHERE epoch <= ?",
                    (current.epoch,),
                )
                self._commit()
            except sqlite3.Error as error:
                raise VoteStoreError(f"CLOSURE NOT RECORDED: {error}") from error
            finally:
                self._rollback_if_open()

            self.committee = following
            self._chain[following.epoch] = following

    def closures(self, after_epoch: int = 0) -> list[EpochClosure]:
        """
        The closures from `after_epoch` on, in order, as far as they are whole. A node that has pruned
        has only headers of old ones, which it never sends, so a peer that far behind needs another.
        """
        with self._lock:
            self._require_open()

            try:
                rows = self._connection.execute(
                    "SELECT closure FROM closures WHERE epoch >= ? ORDER BY epoch",
                    (after_epoch,),
                ).fetchall()
            except sqlite3.Error as error:
                raise VoteStoreError(f"CANNOT READ CLOSURES: {error}") from error

        closures = [_closure_from_text(row[0]) for row in rows]

        if any(isinstance(closure, ClosureHeader) for closure in closures):
            return []

        return closures

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
        self._initial_state = initial_state
        self.state = initial_state.copy()
        self.log: list[QuorumCertificate] = []
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
                continue

            if not self._can_replay(certificate):
                raise VoteStoreError("LOG OF CERTIFICATES DOES NOT REPLAY")
            self._execute(certificate)

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

            for event in pending:
                if self._runs_on(state, ids, event):
                    StateDeriver._apply_one(state, event)
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

            if not self._runs_on(state, ids, event):
                LOG.critical(
                    "the log of this node does not run after a snapshot",
                    extra={"sender": event.sender, "nonce": event.nonce},
                )
                return False

            StateDeriver._apply_one(state, event)
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
        if not self._store.record_vote(event, signed, gathering):
            return None

        return self._signed_vote(event)

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

    @staticmethod
    def _runs_on(state: State, ids: set[str], event: Transfer) -> bool:
        return (
            event.event_id() not in ids
            and set(event.parents) <= ids
            and event.amount > 0
            and event.sender != event.receiver
            and StateDeriver._execution_failure(state, event) is None
        )

    def _is_fresh(self, event: Transfer) -> bool:
        return event.event_id() not in self._executed_ids

    def _is_ready(self, event: Transfer) -> bool:
        return set(event.parents) <= self._executed_ids

    def _is_executable(self, event: Transfer) -> bool:
        return (
            is_executable_event(event)
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
        "EPOCH_CLOSURE",
        "SNAPSHOT_REQUEST",
        "SNAPSHOT_VOTE",
        "SNAPSHOT",
    }
)

# Well under the 16 MiB of a frame. A node that needs more asks again.
SYNC_BATCH_BYTES = 4 * 1024 * 1024
# What a bad signature costs a peer, in tokens of its 5000 per second: 50 of them per second, which
# take under 1% of a core. An honest peer sends none, and it only slows the one that does.
BAD_SIGNATURE_COST = 100
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

        if not self.halted:
            self._resume_gathering()

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

        if message_type == "EPOCH_CLOSURE":
            return self._handle_epoch_closure(decode_epoch_closure(message))

        if message_type == "SNAPSHOT_REQUEST":
            return self._handle_snapshot_request(*decode_snapshot_request(message))

        if message_type == "SNAPSHOT_VOTE":
            return self._handle_snapshot_vote(*decode_snapshot_vote(message))

        if message_type == "SNAPSHOT":
            return self._handle_snapshot(decode_snapshot(message))

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
        report = self.replica.report_epoch(change)

        if report is not None:
            self._reports[report.validator] = report

        closed = self._closure_if_reported()
        return DriverOutput(broadcasts=(encode_epoch_change(change), *closed.broadcasts))

    def retry(self) -> DriverOutput:
        """Call it now and then: what is in progress goes on."""
        epoch = self._retry_epoch()
        snapshot = self._snapshot_tick()
        return DriverOutput(
            broadcasts=(*epoch.broadcasts, *snapshot.broadcasts, *self._resend_requests()),
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
            certificate = self._own_vote_after_a_restart(pending)
            messages.append(
                encode_vote_request(pending.signed)
                if certificate is None
                else encode_certificate(certificate)
            )

        self.requests_resent += len(messages)
        return messages

    def _own_vote_after_a_restart(self, pending: _Resend) -> QuorumCertificate | None:
        """
        Through the same check as any vote. A store restored from a backup refuses, and stays as it
        was: it signs nothing, it gathers the votes of the others, and that needs one more of them.
        """
        if not pending.needs_own_vote:
            return None

        event = pending.signed.transfer
        vote = self.replica.handle_vote_request(event, pending.signed)

        if vote is None:
            return None

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
            report = self.replica.report_epoch(reported)

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
        attestation = self.replica.attest_snapshot(epoch, digest, nonces)

        if attestation is None:
            return _NOTHING

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

        report = self.replica.report_epoch(change)

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
        if self.halted or not self._is_admitted(signed.transfer):
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

        _, votes = self._aggregating.setdefault(event.canonical(), (event, {}))
        votes[vote.validator] = vote
        certificate = self._complete(event, votes)

        if certificate is not None:
            return DriverOutput(broadcasts=(encode_certificate(certificate),))

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
        if not self._is_admitted(signed.transfer):
            return _NOTHING

        if not self._is_authorized(signed):
            self._cost += BAD_SIGNATURE_COST
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
        self._to_resend.pop(event.canonical(), None)
        certificate = QuorumCertificate(
            event,
            tuple(votes[validator] for validator in sorted(votes)),
            self.committee.epoch,
        )
        self._accept(certificate)
        return certificate

    def _handle_certificate(self, certificate: QuorumCertificate) -> DriverOutput:
        if self.halted:
            return _NOTHING

        if self.replica.certificate_is_valid(certificate):
            self._accept(certificate)
        else:
            self._cost += BAD_SIGNATURE_COST

        return _NOTHING

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
            self._buffer.clear()
            self._waiting.clear()
            self._aggregating.clear()
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
    # Events between snapshots, and whether to drop what they cover: see `QuorumDriver`.
    snapshot_every: int | None = None
    prune: bool = False


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
                stays_in_one_asset,
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
        cost = 0
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
                cost += output.cost

        return DriverOutput(tuple(replies), tuple(broadcasts), cost), error

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
            snapshot_every=self._config.snapshot_every,
            prune=self._config.prune,
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
            stays_in_one_asset,
        )
        self.driver = self._new_driver()

    def close(self) -> None:
        if self.closed:
            return

        self.closed = True
        self._store.close()
        os.close(self._lock_file)
