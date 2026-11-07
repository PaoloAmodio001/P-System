"""A process dies at each durable write that matters, and the file says one thing on restart.

The windows are: after the vote is committed but before its signature exists; inside the commit
of a vote; inside the commit of a snapshot; inside the commit of an epoch closure. `SIGKILL`
ends the process and not the operating system, so these tests check the order of operations and
recovery from the SQLite journal, not a power loss.
"""

import signal
import subprocess
import sys

import pytest

from network.quorum import SqliteVoteStore
from tests import quorum_store_worker as worker
from tests.die_with_parent import command

WORKER = worker.__file__


def spawn(mode: str, path, *arguments):
    process = subprocess.Popen(
        command(WORKER, mode, str(path), *map(str, arguments)),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    line = process.stdout.readline().split()
    assert line, process.stderr.read()
    return process, line


def finish(process):
    process.stdout.close()
    process.stderr.close()
    process.wait(timeout=60)
    assert process.returncode == -signal.SIGKILL


def open_worker_store(path, governance=None):
    return SqliteVoteStore(
        path,
        worker.HALT_COMMITTEE,
        worker.HALT_VALIDATOR,
        governance=governance,
    )


def test_a_crash_after_the_vote_and_before_the_signature_keeps_the_lock(tmp_path):
    path = tmp_path / "votes.sqlite"
    process, line = spawn("crash-after-vote-before-sign", path)
    assert line == ["AFTER_VOTE"]
    finish(process)

    store = SqliteVoteStore(path, worker.COMMITTEE, worker.VALIDATOR)
    assert [event.canonical() for event in store.votes()] == [
        worker.event("bob", 0).canonical()
    ]
    assert not store.record_vote(worker.event("carol", 0))
    store.close()


@pytest.mark.parametrize(
    "mode,last,kept",
    [
        ("crash-before-commit", "BEFORE_COMMIT", False),
        ("crash-after-commit", "AFTER_COMMIT", True),
    ],
)
def test_a_crash_inside_the_vote_commit_leaves_one_consistent_state(
    tmp_path, mode, last, kept
):
    path = tmp_path / "votes.sqlite"
    process, line = spawn(mode, path, "bob", 0)
    assert line == ["READY"]
    assert process.stdout.readline().split()[-1] == last
    finish(process)

    store = SqliteVoteStore(path, worker.COMMITTEE, worker.VALIDATOR)
    votes = [event.canonical() for event in store.votes()]
    assert (votes == [worker.event("bob", 0).canonical()]) is kept
    assert store.record_vote(worker.event("carol", 0)) is (not kept)
    store.close()


@pytest.mark.parametrize(
    "mode,last,present",
    [
        ("crash-snapshot-before-commit", "BEFORE_COMMIT", False),
        ("crash-snapshot-after-commit", "AFTER_COMMIT", True),
    ],
)
def test_a_crash_inside_the_snapshot_commit_leaves_one_consistent_state(
    tmp_path, mode, last, present
):
    path = tmp_path / "votes.sqlite"
    process, line = spawn(mode, path)
    assert line[-1] == last
    finish(process)

    store = open_worker_store(path)
    snapshot = store.snapshot()
    assert (snapshot is not None) is present
    if present:
        assert snapshot.digest == worker.SNAPSHOT.digest
        assert snapshot.state.root() == worker.SNAPSHOT.state.root()
    store.close()


@pytest.mark.parametrize(
    "mode,last,installed",
    [
        ("crash-closure-before-commit", "BEFORE_COMMIT", False),
        ("crash-closure-after-commit", "AFTER_COMMIT", True),
    ],
)
def test_a_crash_inside_the_closure_commit_leaves_one_consistent_state(
    tmp_path, mode, last, installed
):
    path = tmp_path / "votes.sqlite"
    process, line = spawn(mode, path)
    assert line[-1] == last
    finish(process)

    store = open_worker_store(path, governance=worker.GOVERNANCE)
    assert (store.committee.epoch == 1) is installed
    assert (len(store.closures()) == 1) is installed
    if installed:
        assert store.closures()[0].change.change_id == worker.CHANGE.change_id
    store.close()
