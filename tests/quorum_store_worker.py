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

from core.attestation import (  # noqa: E402
    Committee,
    EpochChange,
    EpochClosure,
    EpochReport,
    Governance,
    QuorumCertificate,
    Snapshot,
    Vote,
)
from core.event import Transfer  # noqa: E402
from core.signed_event import SignedTransfer  # noqa: E402
from core.state import State  # noqa: E402
from crypto.identity import Identity  # noqa: E402
from network.message import encode_certificate, encode_vote_request  # noqa: E402
from network.node import Node  # noqa: E402
from network.quorum import (  # noqa: E402
    QuorumConfig,
    QuorumRuntime,
    SqliteVoteStore,
)

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
VOTE_SENDER = Identity(Ed25519PrivateKey.from_private_bytes(bytes([21]) * 32))
VOTED_EVENT = Transfer(VOTE_SENDER.identity_id, "bob", 1, 0)
ALTERNATIVE_EVENT = Transfer(VOTE_SENDER.identity_id, "carol", 1, 0)
GOVERNANCE = Governance(tuple(sorted(identity.public_key for identity in HALT_IDENTITIES[:3])), 2)
CHANGE = EpochChange.create(
    HALT_COMMITTEE,
    HALT_MEMBERS,
    1,
    GOVERNANCE,
    HALT_IDENTITIES[:2],
)
REPORTS = tuple(
    EpochReport.create(HALT_COMMITTEE, HALT_IDENTITIES[index], CHANGE.change_id, ())
    for index in (0, 1, 2)
)
CLOSURE = EpochClosure(CHANGE, REPORTS)
SNAPSHOT = Snapshot(0, State(HALT_GENESIS), ())


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


def run_node_mode(mode: str, path: Path) -> None:
    """A real Node, left running until the test kills this process."""
    node = Node(
        "worker-node",
        State(HALT_GENESIS),
        quorum=QuorumConfig(
            HALT_COMMITTEE,
            HALT_IDENTITIES[0],
            path,
            create=True,
        ),
    )

    if mode == "hold-node-halted":
        for event in HALT_EVENTS:
            node._handle_peer_message(
                encode_certificate(signed_certificate(event, (1, 2, 3)))
            )
        report("HALTED", "CONFLICTED" if node.conflicted else "UNIQUE")
    else:
        connection = _ReplyHolder()
        node._handle_peer_message(
            encode_vote_request(SignedTransfer.create(VOTE_SENDER, VOTED_EVENT)),
            connection,
        )
        report("VOTED", connection.sent[0]["signature"])

    signal.pause()


class _ReplyHolder:
    def __init__(self):
        self.sent = []

    def send(self, message):
        self.sent.append(message)

    def enqueue(self, message):

        self.send(message)

        return 0


    def charge(self, tokens):

        pass


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


def run_crash_window(mode: str, path: Path) -> None:
    if mode == "crash-after-vote-before-sign":
        store = SqliteVoteStore(path, COMMITTEE, VALIDATOR, create=True)
        assert store.record_vote(event("bob", 0))
        report("AFTER_VOTE")
        kill_self()

    if mode == "crash-snapshot-before-commit":
        CrashBeforeCommit(path, HALT_COMMITTEE, HALT_VALIDATOR, create=True).record_snapshot(
            SNAPSHOT
        )
        report("NOT_REACHED")

    if mode == "crash-snapshot-after-commit":
        CrashAfterCommit(path, HALT_COMMITTEE, HALT_VALIDATOR, create=True).record_snapshot(
            SNAPSHOT
        )
        report("NOT_REACHED")

    if mode == "crash-closure-before-commit":
        CrashBeforeCommit(
            path, HALT_COMMITTEE, HALT_VALIDATOR, create=True, governance=GOVERNANCE
        ).install_closure(CLOSURE)
        report("NOT_REACHED")

    if mode == "crash-closure-after-commit":
        CrashAfterCommit(
            path, HALT_COMMITTEE, HALT_VALIDATOR, create=True, governance=GOVERNANCE
        ).install_closure(CLOSURE)
        report("NOT_REACHED")


def main() -> None:
    mode, path, *rest = sys.argv[1:]

    if mode.startswith(("crash-after-vote", "crash-snapshot", "crash-closure")):
        run_crash_window(mode, Path(path))
        return

    if mode in ("hold-node-halted", "hold-node-voted"):
        run_node_mode(mode, Path(path))
        return

    if mode == "hold-runtime":
        QuorumRuntime(
            QuorumConfig(
                HALT_COMMITTEE,
                HALT_IDENTITIES[0],
                Path(path),
                create=True,
            ),
            State(HALT_GENESIS),
        )
        report("READY")
        signal.pause()
        return

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
