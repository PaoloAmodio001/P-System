"""
The durable store of a validator: votes, certificates, halt, epochs, snapshots and what it gathers, in SQLite.

Quorum mode: docs/FORMAL-SPECIFICATION.md, section 13.1. The model is in formal/lean/PSystem/Quorum.lean.
"""

import json
import sqlite3
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path

from core.attestation import (
    VOTE,
    ClosureHeader,
    Committee,
    EpochChange,
    EpochClosure,
    Governance,
    QuorumCertificate,
    Snapshot,
    Vote,
    is_authorized_transfer,
)
from core.event import Transfer
from core.signed_event import SignedTransfer
from network.message import (
    decode_epoch_change,
    decode_epoch_closure,
    decode_snapshot_body,
    encode_epoch_change,
    encode_epoch_closure,
    encode_snapshot_body,
)
from network.remote_signer import make_private
from network.quorum import lean_core
from network.quorum.common import VoteStoreError


_SCHEMA_VERSION = "8"
_SCHEMA_VERSION_7 = "7"
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

# What schema 8 adds: the rounds of each key (formal/lean/PSystem/QuorumRounds.lean), written before
# any signature they allow, and the decisions held but not executed yet, which a restart must not lose:
# they are what a conflict after a restart is detected with.
_ROUND_TABLES = (
    """
    CREATE TABLE IF NOT EXISTS rounds (
        epoch INTEGER NOT NULL,
        sender TEXT NOT NULL,
        nonce TEXT NOT NULL,
        state TEXT NOT NULL,
        PRIMARY KEY (epoch, sender, nonce)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS decided (
        event_id TEXT PRIMARY KEY,
        canonical TEXT NOT NULL,
        signatures TEXT NOT NULL,
        epoch INTEGER NOT NULL
    )
    """,
    # The values this validator voted for in a later round, precommitted or decided, in each epoch, with
    # the proof that the sender signed them: its report for the closure holds them as well as its votes
    # of round 0, so that a decided value is in any closure (`voted_in_closure`).
    """
    CREATE TABLE IF NOT EXISTS round_evidence (
        epoch INTEGER NOT NULL,
        event_id TEXT NOT NULL,
        canonical TEXT NOT NULL,
        public_key TEXT NOT NULL,
        signature TEXT NOT NULL,
        PRIMARY KEY (epoch, event_id)
    )
    """,
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
    *_ROUND_TABLES,
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
    """Votes of round 0 as a list, as before schema 8; the other phases with their round."""
    votes = [[vote.validator, vote.signature.hex()] for vote in certificate.votes]
    if certificate.phase == VOTE:
        return json.dumps(votes, separators=(",", ":"))
    return json.dumps(
        {"phase": certificate.phase, "round": certificate.round, "votes": votes},
        separators=(",", ":"),
    )


def _certificate_from_row(
    canonical: str,
    signatures: str,
    epoch: int = 0,
) -> QuorumCertificate:
    data = json.loads(signatures)
    phase, round_ = VOTE, 0
    if type(data) is dict:
        phase, round_, data = data["phase"], data["round"], data["votes"]
    return QuorumCertificate(
        _event_from_canonical(canonical),
        tuple(
            Vote(validator, bytes.fromhex(signature))
            for validator, signature in data
        ),
        epoch,
        phase,
        round_,
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
    if not (
        first.verify(committee_of(first))
        and second.verify(committee_of(second))
        and first.event.sender == second.event.sender
        and first.event.nonce == second.event.nonce
        and first.event.canonical() != second.event.canonical()
    ):
        return False

    # Two decisions, or two prepare certificates of one round: `decisions_agree` and
    # `prepared_same_round` exclude both. A prepare certificate and a later decision for another
    # value are not a proof: a value prepared and never decided can lose a later round.
    if first.decides(committee_of(first)) and second.decides(committee_of(second)):
        return True

    return first.prepares() and second.prepares() and first.round == second.round


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
            elif version not in (
                _SCHEMA_VERSION, _SCHEMA_VERSION_7, _SCHEMA_VERSION_6, _SCHEMA_VERSION_5, _SCHEMA_VERSION_4
            ):
                raise VoteStoreError("UNSUPPORTED VERSION OF THE VOTE STORE")

            if version not in (_SCHEMA_VERSION, _SCHEMA_VERSION_7, _SCHEMA_VERSION_6, _SCHEMA_VERSION_5):
                for statement in _SNAPSHOT_TABLES:
                    self._connection.execute(statement)

                self._drop_closure_votes()

            if version != _SCHEMA_VERSION:
                if version not in (_SCHEMA_VERSION_7, _SCHEMA_VERSION_6):
                    self._connection.execute(_GATHERING_TABLE)

                for statement in _ROUND_TABLES:
                    self._connection.execute(statement)

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
        round_state: dict | None = None,
    ) -> bool:
        """
        Apply the vote lock, `voteAllowed` and `lockAllows` in the model. False means that a
        different event holds the `(sender, nonce)` or the id in this epoch, or a lock from
        an earlier epoch, or that this epoch is closed, or that the node has halted, even
        for an event it already voted for. True means that this event is durably recorded,
        possibly by an earlier call.

        `signed` is the proof to report at the end of the epoch. `gathering`: this node took the event
        and asks votes for it, and that is written with the vote: see `gathering`. `round_state`: the
        rounds of the key with this vote as the vote of round 0, written in the same transaction.

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

                rows = sorted(
                    self._connection.execute(
                        """
                        SELECT canonical, event_id FROM votes
                        WHERE epoch = ? AND ((sender = ? AND nonce = ?) OR event_id = ?)
                        """,
                        (epoch, event.sender, str(event.nonce), event_id),
                    ).fetchall()
                )
                existing = {row[0] for row in rows}

                # The lock is `Quorum.voteAllowed` of the Lean core, given the votes with this key or
                # this id: the answer it gives on all of them (`Core.voteAllowed_local`).
                if rows and not lean_core.vote_allowed(
                    [(_event_from_canonical(other), other_id) for other, other_id in rows], event
                ):
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

                if round_state is not None:
                    self._write_round_state(epoch, event.sender, event.nonce, round_state)

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

    # Rounds: formal/lean/PSystem/QuorumRounds.lean.

    def _write_round_state(self, epoch: int, sender: str, nonce: int, state: dict) -> None:
        self._connection.execute(
            "INSERT OR REPLACE INTO rounds (epoch, sender, nonce, state) VALUES (?, ?, ?, ?)",
            (epoch, sender, str(nonce), json.dumps(state, sort_keys=True, separators=(",", ":"))),
        )

    def round_state(self, sender: str, nonce: int) -> dict | None:
        """The rounds of a key in this epoch, as `Rounds.RState` encodes them, or None."""
        with self._lock:
            self._require_open()

            try:
                row = self._connection.execute(
                    "SELECT state FROM rounds WHERE epoch = ? AND sender = ? AND nonce = ?",
                    (self.committee.epoch, sender, str(nonce)),
                ).fetchone()
            except sqlite3.Error as error:
                raise VoteStoreError(f"CANNOT READ ROUNDS: {error}") from error

        return None if row is None else json.loads(row[0])

    def round_states(self) -> list[tuple[str, int, dict]]:
        """Every key with rounds in this epoch."""
        with self._lock:
            self._require_open()

            try:
                rows = self._connection.execute(
                    "SELECT sender, nonce, state FROM rounds WHERE epoch = ? ORDER BY rowid",
                    (self.committee.epoch,),
                ).fetchall()
            except sqlite3.Error as error:
                raise VoteStoreError(f"CANNOT READ ROUNDS: {error}") from error

        return [(sender, int(nonce), json.loads(state)) for sender, nonce, state in rows]

    def record_round_state(self, sender: str, nonce: int, state: dict) -> bool:
        """
        Write the rounds of a key. True means it is durable and the signatures it allows may
        follow; False that this node has halted or closed the epoch, and signs nothing more.
        Raises when nothing can be said about the write.
        """
        with self._lock:
            self._require_open()

            try:
                self._begin()

                if self._is_halted() or self._is_closed(self.committee.epoch):
                    return False

                self._write_round_state(self.committee.epoch, sender, nonce, state)
                self._commit()
                return True
            except sqlite3.Error as error:
                raise VoteStoreError(f"ROUNDS NOT RECORDED: {error}") from error
            finally:
                self._rollback_if_open()

    def hold_decided(self, certificate: QuorumCertificate) -> None:
        """A decision that cannot run yet. Kept until it runs, so that a restart still knows it."""
        event = certificate.event

        with self._lock:
            self._require_open()

            try:
                self._begin()
                self._connection.execute(
                    """
                    INSERT OR IGNORE INTO decided (event_id, canonical, signatures, epoch)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        event.event_id(),
                        event.canonical().decode(),
                        _encode_signatures(certificate),
                        certificate.epoch,
                    ),
                )
                self._commit()
            except sqlite3.Error as error:
                raise VoteStoreError(f"DECISION NOT RECORDED: {error}") from error
            finally:
                self._rollback_if_open()

    def record_round_evidence(self, signed: SignedTransfer) -> None:
        """A value voted for in rounds or decided in this epoch, signed by its sender, for the closure."""
        event = signed.transfer

        with self._lock:
            self._require_open()

            try:
                self._begin()
                self._connection.execute(
                    """
                    INSERT OR IGNORE INTO round_evidence (epoch, event_id, canonical, public_key, signature)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        self.committee.epoch,
                        event.event_id(),
                        event.canonical().decode(),
                        signed.public_key.hex(),
                        signed.signature.hex(),
                    ),
                )
                self._commit()
            except sqlite3.Error as error:
                raise VoteStoreError(f"DECISION NOT RECORDED: {error}") from error
            finally:
                self._rollback_if_open()

    def decided_held(self) -> list[QuorumCertificate]:
        """The decisions held and not executed, oldest first. Not verified: the caller checks them."""
        with self._lock:
            self._require_open()

            try:
                rows = self._connection.execute(
                    "SELECT canonical, signatures, epoch FROM decided ORDER BY rowid"
                ).fetchall()
            except sqlite3.Error as error:
                raise VoteStoreError(f"CANNOT READ DECISIONS: {error}") from error

        return [_certificate_from_row(*row) for row in rows]

    def signed_vote(self, sender: str, nonce: int) -> SignedTransfer | None:
        """This validator's vote for a key in this epoch, with the proof its sender signed it."""
        with self._lock:
            self._require_open()

            try:
                row = self._connection.execute(
                    """
                    SELECT votes.canonical, vote_evidence.public_key, vote_evidence.signature
                    FROM votes JOIN vote_evidence
                    ON vote_evidence.epoch = votes.epoch AND vote_evidence.event_id = votes.event_id
                    WHERE votes.epoch = ? AND votes.sender = ? AND votes.nonce = ?
                    """,
                    (self.committee.epoch, sender, str(nonce)),
                ).fetchone()
            except sqlite3.Error as error:
                raise VoteStoreError(f"CANNOT READ VOTES: {error}") from error

        if row is None:
            return None
        return SignedTransfer(_event_from_canonical(row[0]), bytes.fromhex(row[1]), bytes.fromhex(row[2]))

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
                self._connection.execute(
                    "DELETE FROM decided WHERE event_id = ?",
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

                # And the values it voted for in later rounds or decided, which may not be among its votes.
                voted = {row[0] for row in rows}
                rows += [
                    row
                    for row in self._connection.execute(
                        "SELECT canonical, public_key, signature FROM round_evidence WHERE epoch = ? ORDER BY rowid",
                        (epoch,),
                    ).fetchall()
                    if row[0] not in voted
                ]

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
