"""
Quorum mode: docs/FORMAL-SPECIFICATION.md, section 13.1.

The model is in formal/lean/PSystem/Quorum.lean. The link between the two is
empirical, not a refinement proof.
"""

import json
import sqlite3
import threading
from collections.abc import Callable
from pathlib import Path

from core.attestation import (
    Committee,
    QuorumCertificate,
    Vote,
    is_well_formed_event,
)
from core.derive import StateDeriver
from core.event import Transfer
from core.state import State
from crypto.identity import Identity


class VoteStoreError(Exception):
    """
    The store cannot be trusted or could not record a write.

    Not a ValueError on purpose: a caller must not treat a failure to record as a
    malformed message. No signature may follow it.
    """


_SCHEMA_VERSION = "1"

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


class SqliteVoteStore:
    """
    The durable part of a validator: its votes and its log of certificates.

    `record_vote` is the vote lock, `voteAllowed` in the model. When it returns
    True the vote is committed, so a signature may follow; a signature must never
    come first. Losing the votes breaks safety, and a node that does has to be
    counted among the faulty ones. Losing the log does not, because in the model
    votes and log are independent.

    A missing file is an error unless `create` is true, so that a deleted file
    does not silently become a validator with no votes. This cannot detect an old
    backup put back in place, which is the same loss.
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

            if found != expected:
                raise VoteStoreError("VOTE STORE BELONGS TO ANOTHER VALIDATOR")
        finally:
            self._rollback_if_open()

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
        `(sender, nonce)` or the id. True means that this event is durably
        recorded, possibly by an earlier call.

        Raises instead of returning when nothing can be said about the write;
        no signature may follow an exception.
        """
        canonical = event.canonical().decode()
        event_id = event.event_id()

        with self._lock:
            self._require_open()

            try:
                self._begin()

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
        signatures = json.dumps(
            [[vote.validator, vote.signature.hex()] for vote in certificate.votes],
            separators=(",", ":"),
        )

        with self._lock:
            self._require_open()

            try:
                self._begin()
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
            QuorumCertificate(
                _event_from_canonical(canonical),
                tuple(
                    Vote(validator, bytes.fromhex(signature))
                    for validator, signature in json.loads(signatures)
                ),
            )
            for canonical, signatures in rows
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
        """Execute the certificate if it can run now. True if it was executed."""
        if not self._can_execute(certificate):
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
