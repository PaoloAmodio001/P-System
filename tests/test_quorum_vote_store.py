"""Durable votes (network/quorum.py).

record_vote must follow voteAllowed in formal/lean/PSystem/Quorum.lean, and what
it accepted must survive the death of the process.

Limit of these tests: SIGKILL ends the process but not the operating system, so
data still in the kernel's page cache survive it. They test recovery and the
order of operations, not the disk. That is why the synchronous setting is tested
on its own, and a power loss is not tested at all.
"""

import os
import random
import signal
import sqlite3
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from core.attestation import Committee, QuorumCertificate, Vote
from core.event import Transfer
from core.state import State
from network.quorum import SqliteVoteStore, VoteStoreError
from tests import quorum_store_worker as worker

COMMITTEE = worker.COMMITTEE
VALIDATOR = worker.VALIDATOR
WORKER = Path(worker.__file__)

A = Transfer("alice", "bob", 8, 0)
B = Transfer("alice", "carol", 8, 0)


class FixedIdTransfer(Transfer):
    """A hash collision, which SHA-256 cannot produce on demand."""

    def event_id(self) -> str:
        return "f" * 64


@pytest.fixture
def path(tmp_path) -> Path:
    return tmp_path / "votes.sqlite"


@pytest.fixture
def store(path):
    opened = SqliteVoteStore(path, COMMITTEE, VALIDATOR, create=True)
    yield opened
    opened.close()


def reopen(path: Path) -> SqliteVoteStore:
    return SqliteVoteStore(path, COMMITTEE, VALIDATOR)


def canonical_set(events) -> set[bytes]:
    return {event.canonical() for event in events}


# --- The rule of voteAllowed ---------------------------------------------


def test_first_vote_is_allowed(store):
    assert store.record_vote(A)
    assert canonical_set(store.votes()) == {A.canonical()}


def test_conflicting_vote_is_refused_and_not_recorded(store):
    assert store.record_vote(A)
    assert not store.record_vote(B)
    assert canonical_set(store.votes()) == {A.canonical()}


def test_the_other_order_locks_the_other_event(store):
    assert store.record_vote(B)
    assert not store.record_vote(A)
    assert canonical_set(store.votes()) == {B.canonical()}


def test_same_event_again_is_allowed_and_recorded_once(store):
    assert store.record_vote(A)
    assert store.record_vote(A)
    assert len(store.votes()) == 1


def test_permuted_parents_are_the_same_event(store):
    first = Transfer("alice", "bob", 1, 0, ("a" * 64, "b" * 64))
    second = Transfer("alice", "bob", 1, 0, ("b" * 64, "a" * 64))
    assert store.record_vote(first)
    assert store.record_vote(second)
    assert len(store.votes()) == 1


def test_other_nonces_and_senders_are_free(store):
    assert store.record_vote(A)
    assert store.record_vote(Transfer("alice", "bob", 8, 1))
    assert store.record_vote(Transfer("dave", "bob", 8, 0))
    assert len(store.votes()) == 3


def test_same_id_with_other_content_is_refused(store):
    # The id lock of voteAllowed: different key, same id.
    first = FixedIdTransfer("alice", "bob", 1, 0)
    second = FixedIdTransfer("dave", "carol", 2, 5)
    assert store.record_vote(first)
    assert not store.record_vote(second)
    assert len(store.votes()) == 1


def test_nonce_beyond_64_bits_is_locked_too(store):
    # Lean nonces are unbounded; an SQLite integer is not.
    nonce = 2**64 + 1
    assert store.record_vote(Transfer("alice", "bob", 1, nonce))
    assert not store.record_vote(Transfer("alice", "carol", 1, nonce))
    assert store.record_vote(Transfer("alice", "carol", 1, nonce + 1))
    assert {event.nonce for event in store.votes()} == {nonce, nonce + 1}


def test_votes_are_read_back_as_the_same_events(store):
    event = Transfer("alice", "bob", 3, 7, ("b" * 64, "a" * 64))
    assert store.record_vote(event)
    [read] = store.votes()
    assert read.canonical() == event.canonical()
    assert read.event_id() == event.event_id()
    assert (read.sender, read.receiver, read.amount, read.nonce) == (
        "alice", "bob", 3, 7,
    )


# --- Restart and opening -------------------------------------------------


def test_lock_survives_reopening(path, store):
    assert store.record_vote(A)
    store.close()
    second = reopen(path)
    assert not second.record_vote(B)
    assert second.record_vote(A)
    assert canonical_set(second.votes()) == {A.canonical()}
    second.close()


def test_missing_file_is_refused_without_create(path):
    # Otherwise a deleted file would silently become a validator with no votes.
    with pytest.raises(VoteStoreError):
        reopen(path)
    assert not path.exists()


def test_deleted_file_is_refused(path, store):
    assert store.record_vote(A)
    store.close()
    path.unlink()
    with pytest.raises(VoteStoreError):
        reopen(path)


def test_empty_file_is_refused_without_create(path):
    path.touch()
    with pytest.raises(VoteStoreError):
        reopen(path)


def test_file_that_is_not_a_store_is_refused(path):
    path.write_bytes(b"not a database" * 100)
    for create in (False, True):
        with pytest.raises(VoteStoreError):
            SqliteVoteStore(path, COMMITTEE, VALIDATOR, create=create)


def test_database_of_another_application_is_refused(path):
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE other (x)")
    connection.commit()
    connection.close()
    for create in (False, True):
        with pytest.raises(VoteStoreError):
            SqliteVoteStore(path, COMMITTEE, VALIDATOR, create=create)


def test_create_on_an_existing_store_keeps_its_votes(path, store):
    assert store.record_vote(A)
    store.close()
    again = SqliteVoteStore(path, COMMITTEE, VALIDATOR, create=True)
    assert not again.record_vote(B)
    again.close()


def test_store_of_another_committee_is_refused(path, store):
    store.close()
    other = Committee(worker.MEMBERS, 1, State({"alice": 1}).root())
    for create in (False, True):
        with pytest.raises(VoteStoreError):
            SqliteVoteStore(path, other, VALIDATOR, create=create)


def test_store_of_another_validator_is_refused(path, store):
    store.close()
    for create in (False, True):
        with pytest.raises(VoteStoreError):
            SqliteVoteStore(path, COMMITTEE, worker.MEMBERS[1], create=create)


def test_validator_must_be_a_member(path):
    with pytest.raises(VoteStoreError):
        SqliteVoteStore(path, COMMITTEE, b"\x09" * 32, create=True)
    assert not path.exists()


# --- Durability settings -------------------------------------------------


def test_durability_settings(store):
    # EXTRA also syncs the directory after the journal is unlinked. With FULL a
    # power loss right after a commit could bring the journal back, and the
    # commit would be rolled back after the signature went out.
    assert store._pragma("synchronous") == 3  # EXTRA
    assert store._pragma("journal_mode") == "delete"


@pytest.mark.parametrize(
    "setting,reported",
    [("synchronous", 2), ("synchronous", 0), ("journal_mode", "wal")],
)
def test_store_refuses_to_open_if_a_setting_did_not_apply(path, setting, reported):
    # SQLite can decline a pragma without an error, for example a journal mode.
    class NotApplied(SqliteVoteStore):
        def _pragma(self, name):
            return reported if name == setting else super()._pragma(name)

    with pytest.raises(VoteStoreError):
        NotApplied(path, COMMITTEE, VALIDATOR, create=True)


# --- Failures keep the store closed --------------------------------------


def _fill_up(store) -> None:
    store._connection.execute(
        "PRAGMA max_page_count = " + str(store._pragma("page_count"))
    )


def test_full_disk_refuses_with_an_error_and_records_nothing(path, store):
    _fill_up(store)
    with pytest.raises(VoteStoreError):
        for nonce in range(10_000):
            store.record_vote(Transfer("alice", "x" * 2000, 1, nonce))

    recorded = canonical_set(store.votes())
    store.close()

    second = reopen(path)
    assert canonical_set(second.votes()) == recorded
    second.close()


def test_store_works_again_after_a_failed_write(store):
    limit = store._pragma("page_count")
    _fill_up(store)
    with pytest.raises(VoteStoreError):
        for nonce in range(10_000):
            store.record_vote(Transfer("alice", "x" * 2000, 1, nonce))

    store._connection.execute(f"PRAGMA max_page_count = {limit + 10_000}")
    assert store.record_vote(Transfer("dave", "bob", 1, 0))


def test_invalid_text_is_an_error_and_records_nothing(store):
    with pytest.raises(ValueError):
        store.record_vote(Transfer("alice\udc80", "bob", 1, 0))
    assert store.votes() == []


def test_closed_store_refuses(path, store):
    store.close()
    with pytest.raises(VoteStoreError):
        store.record_vote(A)
    with pytest.raises(VoteStoreError):
        store.votes()


def test_close_twice_is_harmless(store):
    store.close()
    store.close()


# --- Concurrency ---------------------------------------------------------


def test_threads_on_one_store_lock_one_winner(store):
    results = {}
    barrier = threading.Barrier(8)

    def attempt(label: str) -> None:
        barrier.wait()
        results[label] = store.record_vote(Transfer("alice", label, 1, 0))

    threads = [
        threading.Thread(target=attempt, args=(f"r{i}",)) for i in range(8)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sum(results.values()) == 1
    assert len(store.votes()) == 1


def test_a_vote_holds_the_write_lock_from_the_start(path, store):
    # The check and the write are one step. Without this a second process would
    # still be stopped by the unique constraints, but with an error, not a refusal.
    store._begin()
    other = sqlite3.connect(path, isolation_level=None, timeout=0)
    try:
        with pytest.raises(sqlite3.OperationalError):
            other.execute("BEGIN IMMEDIATE")
    finally:
        other.close()
        store._rollback_if_open()


def _spawn(mode: str, path: Path, *args) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, str(WORKER), mode, str(path), *map(str, args)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def test_two_processes_lock_one_winner_per_nonce(path, store):
    # Two processes with one file, as after a mistaken double start.
    store.close()
    count = 40
    first = _spawn("race", path, "left", count)
    second = _spawn("race", path, "right", count)
    outputs = [process.communicate(timeout=120) for process in (first, second)]
    assert first.returncode == 0, outputs[0][1]
    assert second.returncode == 0, outputs[1][1]

    wins = {"left": set(), "right": set()}
    for label, (stdout, _) in zip(("left", "right"), outputs):
        for line in stdout.splitlines():
            if line.startswith("RESULT"):
                _, nonce, won = line.split()
                if won == "1":
                    wins[label].add(int(nonce))

    assert not wins["left"] & wins["right"]
    assert wins["left"] | wins["right"] == set(range(count))

    final = reopen(path)
    assert len(final.votes()) == count
    for event in final.votes():
        assert event.nonce in wins[event.receiver]
    final.close()


# --- Crashes -------------------------------------------------------------


def _finish(process: subprocess.Popen) -> list[str]:
    stdout, stderr = process.communicate(timeout=60)
    assert process.returncode == -signal.SIGKILL, stderr
    return stdout.splitlines()


def test_crash_after_commit_keeps_the_vote(path):
    process = _spawn("crash-after-commit", path, "bob", 0)
    assert _finish(process)[-1] == "AFTER_COMMIT"

    store = reopen(path)
    assert canonical_set(store.votes()) == {worker.event("bob", 0).canonical()}
    assert not store.record_vote(worker.event("carol", 0))
    assert store.record_vote(worker.event("bob", 0))
    store.close()


def test_crash_before_commit_loses_only_an_unsigned_vote(path):
    # No signature can have left, so the alternative is still free. The file is
    # left with an open transaction and a journal to recover from.
    process = _spawn("crash-before-commit", path, "bob", 0)
    assert _finish(process)[-1] == "BEFORE_COMMIT"
    assert Path(str(path) + "-journal").exists()

    store = reopen(path)
    assert store.votes() == []
    assert store.record_vote(worker.event("carol", 0))
    assert not store.record_vote(worker.event("bob", 0))
    store.close()


def test_kill_at_random_moments_never_loses_an_acknowledged_vote(path):
    rng = random.Random(20261103)
    acknowledged: set[int] = set()
    before: set[int] = set()
    next_nonce = 0

    for _ in range(8):
        process = _spawn("vote-loop", path, "bob", next_nonce)
        seen = []
        target = rng.randint(1, 25)
        assert process.stdout.readline().strip() == "READY"
        while len(seen) < target:
            line = process.stdout.readline()
            assert line.startswith("ACK"), line + process.stderr.read()
            seen.append(int(line.split()[1]))
        process.send_signal(signal.SIGKILL)
        # Through the same stream: readline may already hold further lines in its
        # buffer, and communicate() would read past them and lose them.
        seen += [
            int(line.split()[1])
            for line in process.stdout.read().splitlines()
            if line.startswith("ACK")
        ]
        process.stdout.close()
        process.stderr.close()
        process.wait(timeout=60)
        acknowledged.update(seen)

        store = reopen(path)
        nonces = {event.nonce for event in store.votes()}
        assert acknowledged <= nonces
        # At most the one vote in flight when this process died is extra. Earlier
        # processes may each have left theirs, committed but not acknowledged.
        assert len(nonces - acknowledged - before) <= 1
        for nonce in sorted(acknowledged):
            assert not store.record_vote(worker.event("carol", nonce))
        next_nonce = max(nonces) + 1
        before = nonces
        store.close()


# --- Certificates --------------------------------------------------------


def _certificate(event: Transfer, *validators: int) -> QuorumCertificate:
    return QuorumCertificate(
        event,
        tuple(Vote(index, bytes([index]) * 64) for index in validators),
    )


def test_certificates_keep_their_order_across_reopening(path, store):
    first = _certificate(Transfer("alice", "bob", 1, 0), 0, 1, 2)
    second = _certificate(Transfer("alice", "bob", 1, 1, ("c" * 64,)), 1, 2, 3)
    third = _certificate(Transfer("zed", "bob", 1, 0), 3, 0, 2)
    for certificate in (second, third, first):
        store.append_certificate(certificate)
    store.close()

    again = reopen(path)
    read = again.certificates()
    again.close()

    assert [c.event.canonical() for c in read] == [
        c.event.canonical() for c in (second, third, first)
    ]
    assert [c.votes for c in read] == [c.votes for c in (second, third, first)]


def test_same_certified_event_twice_is_an_error(store):
    # The replica never executes an id twice, so this would be a bug there.
    store.append_certificate(_certificate(A, 0, 1, 2))
    with pytest.raises(VoteStoreError):
        store.append_certificate(_certificate(A, 1, 2, 3))
    assert len(store.certificates()) == 1


def test_votes_and_certificates_are_independent(store):
    # Executing an event does not count as voting for it, as in the model.
    store.append_certificate(_certificate(A, 0, 1, 2))
    assert store.votes() == []
    assert store.record_vote(B)
