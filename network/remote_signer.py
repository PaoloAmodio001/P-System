"""
The key of a validator in another process, which refuses to sign two votes for one spend.

A node holds its private key in memory, so a bug or an intruder in the node gets the key and can sign
anything. With this signer the node holds no key, and the signer keeps a second, independent vote
lock. A node that is taken over can ask for signatures, but no more than one for each
`(committee, sender, nonce)` on any event, whatever its own files say, also after restoring an old
backup. It cannot make this validator equivocate, and only that would help a fork.

The guard is durable against the death of the process. It is not against a power cut: the last
signatures can be forgotten. The vote lock in the store of the node stays the rule that the proofs are
about, with the full durability, and this is a second defense behind it. So it can only refuse more.

What the signer does not check: the locks of earlier epochs, the balance, anything else of the
protocol. A faulty node can still vote for an event once, as any faulty member can.

The socket is a Unix one: this keeps the key away from the process, not from the machine. An HSM or a
KMS would take the place of `SignerServer`, with the same rule. None has been integrated or tested.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import sqlite3
import stat
import threading
from pathlib import Path

LOG = logging.getLogger("psystem.signer")

# Written here and not imported from core.attestation, whose signatures are what this guards: a
# change of the format must make the signer refuse, not sign something it no longer understands.
VOTE_DOMAIN = b"P-SYSTEM/QUORUM-VOTE/v1\0"
EPOCH_REPORT_DOMAIN = b"P-SYSTEM/EPOCH-REPORT/v1\0"
SNAPSHOT_DOMAIN = b"P-SYSTEM/SNAPSHOT/v1\0"
ID_SIZE = 32
SIGNATURE_SIZE = 64
MAX_REQUEST = 1024 * 1024
_ASK_KEY = b"K"
_ASK_SIGNATURE = b"S"
_GRANTED = b"Y"
_REFUSED = b"N"


class SignerUnavailable(Exception):
    """No signature came: refused, or the signer cannot be reached."""


class SignerGuard:
    """What this key has signed. Every refusal is on the record of the signer, in its log."""

    def __init__(self, path: Path) -> None:
        self._connection = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.execute("PRAGMA synchronous = NORMAL")
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS votes (
                committee TEXT NOT NULL,
                sender TEXT NOT NULL,
                nonce TEXT NOT NULL,
                canonical BLOB NOT NULL,
                PRIMARY KEY (committee, sender, nonce)
            )
            """
        )
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS reports (
                committee TEXT NOT NULL,
                change_id TEXT NOT NULL,
                digest BLOB NOT NULL,
                PRIMARY KEY (committee, change_id)
            )
            """
        )

    def _first_or_same(self, insert: str, select: str, key: tuple, value: bytes) -> bool:
        self._connection.execute(insert, (*key, value))
        row = self._connection.execute(select, key).fetchone()
        return row[0] == value

    def permit(self, payload: bytes) -> bool:
        """True if this payload may be signed, and from now on nothing that conflicts with it."""
        if payload.startswith(VOTE_DOMAIN):
            return self._permit_vote(payload[len(VOTE_DOMAIN):])

        if payload.startswith(EPOCH_REPORT_DOMAIN):
            return self._permit_report(payload[len(EPOCH_REPORT_DOMAIN):])

        # A snapshot is a claim about a state, with no lock to break: two can both be true. The signer
        # cannot recompute it, so a node taken over can make it sign a false one, as any faulty
        # member can. That is what the quorum of signatures on a snapshot is for.
        if payload.startswith(SNAPSHOT_DOMAIN):
            return len(payload) == len(SNAPSHOT_DOMAIN) + 3 * ID_SIZE

        return False

    def _permit_vote(self, body: bytes) -> bool:
        committee, canonical = body[:ID_SIZE], body[ID_SIZE:]

        try:
            event = json.loads(canonical)
            sender, nonce = event["sender"], event["nonce"]
        except (ValueError, KeyError, TypeError):
            return False

        if len(committee) != ID_SIZE or type(sender) is not str or type(nonce) is not int:
            return False

        return self._first_or_same(
            """
            INSERT OR IGNORE INTO votes (committee, sender, nonce, canonical)
            VALUES (?, ?, ?, ?)
            """,
            "SELECT canonical FROM votes WHERE committee = ? AND sender = ? AND nonce = ?",
            (committee.hex(), sender, str(nonce)),
            canonical,
        )

    def _permit_report(self, body: bytes) -> bool:
        if len(body) != 3 * ID_SIZE:
            return False

        committee, change_id, digest = body[:ID_SIZE], body[ID_SIZE:2 * ID_SIZE], body[2 * ID_SIZE:]
        return self._first_or_same(
            """
            INSERT OR IGNORE INTO reports (committee, change_id, digest)
            VALUES (?, ?, ?)
            """,
            "SELECT digest FROM reports WHERE committee = ? AND change_id = ?",
            (committee.hex(), change_id.hex()),
            digest,
        )

    def close(self) -> None:
        self._connection.close()


def _read_exact(connection: socket.socket, size: int) -> bytes:
    data = bytearray()

    while len(data) < size:
        chunk = connection.recv(size - len(data))

        if not chunk:
            raise ConnectionError("SIGNER CONNECTION CLOSED")

        data.extend(chunk)

    return bytes(data)


class SignerServer:
    def __init__(self, identity, socket_path: Path, guard_path: Path) -> None:
        self._identity = identity
        self.public_key = identity.public_key
        self.socket_path = Path(socket_path)
        self._guard = SignerGuard(Path(guard_path))
        self._lock = threading.Lock()
        self._running = False
        self._listener = None
        self._thread = None

    def start(self) -> None:
        # A socket left by a signer that died can go. Anything else at that path is no socket
        # of ours, and it stays.
        if self.socket_path.exists():
            if not stat.S_ISSOCK(self.socket_path.stat().st_mode):
                raise ValueError(f"NOT A SOCKET: {self.socket_path}")
            self.socket_path.unlink()

        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        previous = os.umask(0o177)

        try:
            listener.bind(str(self.socket_path))
        finally:
            os.umask(previous)

        listener.listen()
        self._listener = listener
        self._running = True
        self._thread = threading.Thread(target=self._accept, daemon=True)
        self._thread.start()

    def _accept(self) -> None:
        while self._running:
            try:
                connection, _ = self._listener.accept()
            except OSError:
                return

            threading.Thread(target=self._serve, args=(connection,), daemon=True).start()

    def _serve(self, connection: socket.socket) -> None:
        with connection:
            try:
                while True:
                    kind = _read_exact(connection, 1)

                    if kind == _ASK_KEY:
                        connection.sendall(self.public_key)
                        continue

                    if kind != _ASK_SIGNATURE:
                        return

                    size = int.from_bytes(_read_exact(connection, 4), "big")

                    if not 0 < size <= MAX_REQUEST:
                        return

                    connection.sendall(self._answer(_read_exact(connection, size)))
            except (ConnectionError, OSError, sqlite3.Error) as error:
                # Without the guard there is no signature: the client sees a closed connection.
                LOG.debug("signer connection ended", extra={"reason": str(error)})
                return

    def _answer(self, payload: bytes) -> bytes:
        # In this order under one lock: the guard is on disk before any signature exists.
        with self._lock:
            if not self._guard.permit(payload):
                LOG.error("signature refused", extra={"payload_start": payload[:64].hex()})
                return _REFUSED

            return _GRANTED + self._identity.sign(payload)

    def stop(self) -> None:
        self._running = False

        if self._listener is not None:
            # A blocking accept does not end with close alone.
            try:
                self._listener.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self._listener.close()

        if self._thread is not None:
            self._thread.join(timeout=2)

        self.socket_path.unlink(missing_ok=True)

        with self._lock:
            self._guard.close()


class RemoteIdentity:
    """What the node needs of an identity, with the key in a signer. It reconnects by itself."""

    TIMEOUT = 5.0

    def __init__(self, socket_path: Path) -> None:
        self.socket_path = Path(socket_path)
        self._lock = threading.Lock()
        self._connection: socket.socket | None = None
        self.public_key = self._ask_key()

    @property
    def identity_id(self) -> str:
        from hashlib import sha256

        return sha256(self.public_key).hexdigest()

    def _connected(self) -> socket.socket:
        if self._connection is None:
            connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            connection.settimeout(self.TIMEOUT)
            connection.connect(str(self.socket_path))
            self._connection = connection

        return self._connection

    def _drop(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def _ask_key(self) -> bytes:
        with self._lock:
            try:
                connection = self._connected()
                connection.sendall(_ASK_KEY)
                return _read_exact(connection, ID_SIZE)
            except (ConnectionError, OSError) as error:
                self._drop()
                raise SignerUnavailable(f"CANNOT REACH THE SIGNER: {error}") from error

    def sign(self, data: bytes) -> bytes:
        with self._lock:
            try:
                connection = self._connected()
                connection.sendall(_ASK_SIGNATURE + len(data).to_bytes(4, "big") + data)
                answer = _read_exact(connection, 1)

                if answer == _REFUSED:
                    raise SignerUnavailable("THE SIGNER REFUSED")

                if answer != _GRANTED:
                    self._drop()
                    raise SignerUnavailable("THE SIGNER ANSWERED NOTHING KNOWN")

                return _read_exact(connection, SIGNATURE_SIZE)
            except (ConnectionError, OSError) as error:
                self._drop()
                raise SignerUnavailable(f"CANNOT REACH THE SIGNER: {error}") from error
