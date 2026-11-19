"""
The configuration of a validator, and the replica and driver it runs.

Quorum mode: docs/FORMAL-SPECIFICATION.md, section 13.1. The model is in formal/lean/PSystem/Quorum.lean.
"""

import os
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from core.attestation import (
    Committee,
    Governance,
    stays_in_one_asset,
)
from core.signed_event import SignedTransfer
from core.state import State
from crypto.identity import Identity
from network.quorum.common import VoteStoreError
from network.quorum.store import SqliteVoteStore
from network.quorum.replica import QuorumReplica
from network.quorum.driver import (
    DriverOutput,
    QuorumDriver,
)


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
