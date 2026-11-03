"""Worker process for tests/test_quorum_vote_store.py.

Run as a script so that it can be killed, or kill itself, at a chosen point.
It prints one line for each result, flushed before going on: a line that reaches
the test is a result the store had already returned.
"""

import os
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.attestation import Committee  # noqa: E402
from core.event import Transfer  # noqa: E402
from core.state import State  # noqa: E402
from network.quorum import SqliteVoteStore  # noqa: E402

MEMBERS = tuple(bytes([value]) * 32 for value in (1, 2, 3, 4))
COMMITTEE = Committee(MEMBERS, 1, State({"alice": 1000}).root())
VALIDATOR = MEMBERS[0]


def event(label: str, nonce: int) -> Transfer:
    return Transfer(sender="alice", receiver=label, amount=1, nonce=nonce)


def report(*fields) -> None:
    print(*fields, flush=True)


def kill_self() -> None:
    os.kill(os.getpid(), signal.SIGKILL)


class CrashBeforeCommit(SqliteVoteStore):
    def _commit(self) -> None:
        report("BEFORE_COMMIT")
        kill_self()


class CrashAfterCommit(SqliteVoteStore):
    def _commit(self) -> None:
        super()._commit()
        report("AFTER_COMMIT")
        kill_self()


def main() -> None:
    mode, path, *rest = sys.argv[1:]
    store_type = {
        "crash-before-commit": CrashBeforeCommit,
        "crash-after-commit": CrashAfterCommit,
    }.get(mode, SqliteVoteStore)
    store = store_type(Path(path), COMMITTEE, VALIDATOR, create=True)
    report("READY")

    if mode in ("crash-before-commit", "crash-after-commit"):
        store.record_vote(event(rest[0], int(rest[1])))
        report("NOT_REACHED")
    elif mode == "vote-loop":
        nonce = int(rest[1])
        while True:
            assert store.record_vote(event(rest[0], nonce))
            report("ACK", nonce)
            nonce += 1
    elif mode == "race":
        label, count = rest[0], int(rest[1])
        for nonce in range(count):
            report("RESULT", nonce, int(store.record_vote(event(label, nonce))))
    else:
        raise SystemExit(f"unknown mode {mode}")


if __name__ == "__main__":
    main()
