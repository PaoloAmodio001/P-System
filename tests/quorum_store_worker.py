"""Worker process for tests/test_quorum_vote_store.py.

Run as a script so that it can be killed, or kill itself, at a chosen point.
It prints one line for each result, flushed before going on: a line that reaches
the test is a result the store had already returned.
"""

import os
import signal
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.attestation import Committee, QuorumCertificate, Vote  # noqa: E402
from core.event import Transfer  # noqa: E402
from core.state import State  # noqa: E402
from crypto.identity import Identity  # noqa: E402
from network.quorum import SqliteVoteStore  # noqa: E402

MEMBERS = tuple(bytes([value]) * 32 for value in (1, 2, 3, 4))
COMMITTEE = Committee(MEMBERS, 1, State({"alice": 1000}).root())
VALIDATOR = MEMBERS[0]

# Real keys, fixed so that this process and the test build the same certificates.
HALT_IDENTITIES = sorted(
    (
        Identity(Ed25519PrivateKey.from_private_bytes(bytes([value]) * 32))
        for value in (11, 12, 13, 14)
    ),
    key=lambda identity: identity.public_key,
)
HALT_MEMBERS = tuple(identity.public_key for identity in HALT_IDENTITIES)
HALT_GENESIS = {"alice": 1000}
HALT_COMMITTEE = Committee.create(HALT_MEMBERS, 1, State(HALT_GENESIS))
HALT_VALIDATOR = HALT_MEMBERS[0]
HALT_EVENTS = (
    Transfer("alice", "bob", 8, 0),
    Transfer("alice", "carol", 8, 0),
)


def halt_committee_with_genesis(balances: dict) -> Committee:
    return Committee.create(HALT_MEMBERS, 1, State(balances))


def signed_certificate(event, indexes, committee=HALT_COMMITTEE) -> QuorumCertificate:
    return QuorumCertificate(
        event,
        tuple(Vote.create(committee, HALT_IDENTITIES[i], event) for i in indexes),
    )


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


def run_halt_mode(mode: str, path: Path) -> None:
    store_types = {
        "before-commit": CrashBeforeCommit,
        "after-commit": CrashAfterCommit,
    }

    if mode.startswith("halt-open-crash-"):
        # The file is a store of schema 1: opening it migrates, with a commit.
        store_types[mode.removeprefix("halt-open-crash-")](
            path, HALT_COMMITTEE, HALT_VALIDATOR
        )
    else:
        # Creating the file does not go through _commit, recording the halt does.
        store = store_types[mode.removeprefix("halt-crash-")](
            path, HALT_COMMITTEE, HALT_VALIDATOR, create=True
        )
        store.record_halt(
            signed_certificate(HALT_EVENTS[0], (0, 1, 2)),
            signed_certificate(HALT_EVENTS[1], (1, 2, 3)),
        )

    report("NOT_REACHED")


def main() -> None:
    mode, path, *rest = sys.argv[1:]

    if mode.startswith("halt-"):
        run_halt_mode(mode, Path(path))
        return

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
