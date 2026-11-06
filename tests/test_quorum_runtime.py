"""QuorumRuntime: what a node in quorum mode owns, and the checks made at opening."""

import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from core.state import State
from crypto.identity import Identity
from tests.die_with_parent import command
from network.quorum import QuorumConfig, QuorumRuntime, SqliteVoteStore, VoteStoreError
from tests import quorum_store_worker as worker

GENESIS = State(worker.HALT_GENESIS)
COMMITTEE = worker.HALT_COMMITTEE
IDENTITY = worker.HALT_IDENTITIES[0]


@pytest.fixture
def path(tmp_path) -> Path:
    return tmp_path / "votes.sqlite"


def config(path: Path, create: bool = True, identity=IDENTITY) -> QuorumConfig:
    return QuorumConfig(COMMITTEE, identity, path, create=create)


def test_runtime_opens_store_replica_and_driver(path):
    runtime = QuorumRuntime(config(path), GENESIS)

    assert runtime.driver.replica is runtime.replica
    assert runtime.replica.state.root() == GENESIS.root()
    assert path.exists()
    runtime.close()


def test_wrong_genesis_is_refused_and_leaves_no_file(path, tmp_path):
    with pytest.raises(ValueError):
        QuorumRuntime(config(path), State({"alice": 1}))

    assert list(tmp_path.iterdir()) == []


def test_second_runtime_on_the_same_file_is_refused(path):
    first = QuorumRuntime(config(path), GENESIS)

    with pytest.raises(VoteStoreError):
        QuorumRuntime(config(path), GENESIS)

    first.close()


def test_close_releases_the_lock(path):
    QuorumRuntime(config(path), GENESIS).close()

    again = QuorumRuntime(config(path, create=False), GENESIS)
    again.close()


def test_refused_runtime_does_not_take_the_lock_of_the_first(path):
    first = QuorumRuntime(config(path), GENESIS)

    with pytest.raises(VoteStoreError):
        QuorumRuntime(config(path), GENESIS)

    # The failed attempt closed its own descriptor only, so the lock still holds.
    with pytest.raises(VoteStoreError):
        QuorumRuntime(config(path), GENESIS)

    first.close()


def _open_descriptors() -> int:
    return len(os.listdir("/proc/self/fd"))


def test_failed_opening_releases_lock_and_descriptors(path):
    # Missing file without create: the store fails after the lock was taken.
    before = _open_descriptors()

    with pytest.raises(VoteStoreError):
        QuorumRuntime(config(path, create=False), GENESIS)

    assert _open_descriptors() == before
    QuorumRuntime(config(path), GENESIS).close()


def test_store_that_does_not_replay_releases_the_lock(path):
    # The replica fails after the store is open: a log with a certificate below the
    # quorum does not replay.
    QuorumRuntime(config(path), GENESIS).close()
    before = _open_descriptors()
    store = SqliteVoteStore(path, COMMITTEE, IDENTITY.public_key)
    store.append_certificate(worker.signed_certificate(worker.HALT_EVENTS[0], (0, 1)))
    store.close()

    with pytest.raises(VoteStoreError):
        QuorumRuntime(config(path, create=False), GENESIS)

    assert _open_descriptors() == before


def test_identity_outside_the_committee_is_refused(path):
    with pytest.raises(VoteStoreError):
        QuorumRuntime(config(path, identity=Identity.create()), GENESIS)


def test_close_twice_is_harmless(path):
    runtime = QuorumRuntime(config(path), GENESIS)
    runtime.close()
    runtime.close()
    assert runtime.closed


def test_store_can_still_be_opened_twice_without_a_runtime(path):
    # The lock belongs to the runtime: the store's own guarantee is tested with two
    # processes on one file, and that must keep working.
    runtime = QuorumRuntime(config(path), GENESIS)
    store = SqliteVoteStore(path, COMMITTEE, IDENTITY.public_key)
    store.close()
    runtime.close()


def _spawn_holder(path: Path) -> subprocess.Popen:
    process = subprocess.Popen(
        command(worker.__file__, "hold-runtime", str(path)),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdout.readline().strip() == "READY"
    return process


def test_lock_holds_across_processes_and_ends_with_a_kill(path):
    process = _spawn_holder(path)

    try:
        with pytest.raises(VoteStoreError):
            QuorumRuntime(config(path, create=False), GENESIS)
    finally:
        process.send_signal(signal.SIGKILL)
        process.wait(timeout=10)

    # The kernel released it: no stale lock to remove by hand.
    QuorumRuntime(config(path, create=False), GENESIS).close()
