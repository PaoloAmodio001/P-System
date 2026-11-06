"""How long a restart takes, with and without a snapshot, on real files.

    python -m benchmarks.restart_time 10000 50000

Certificates are signed once and written straight into a store, so what is measured is opening it. Each
count runs three ways: no snapshot, a snapshot that covers all of it, and the same after pruning. It
prints one JSON line for each. Memory is the peak of this process over the whole run, so it is only
an upper bound for each line.
"""

import json
import resource
import sys
import tempfile
import time
from pathlib import Path

from core.attestation import Committee, QuorumCertificate, Snapshot, SnapshotAttestation, Vote
from core.event import Transfer
from core.state import State
from crypto.identity import Identity
from network.quorum import QuorumReplica, SqliteVoteStore


def open_replica(path, committee, member, genesis, create=False):
    store = SqliteVoteStore(path, committee, member.public_key, create=create)
    return QuorumReplica(member, genesis, store, lambda _event: True)


def timed_open(path, committee, member, genesis) -> tuple[float, int]:
    started = time.perf_counter()
    replica = open_replica(path, committee, member, genesis)
    seconds = time.perf_counter() - started
    root = replica.state.root()
    replica._store.close()
    return seconds, root


def measure(count: int) -> list[dict]:
    sender = Identity.create()
    genesis = State({sender.identity_id: 10**12})
    members = sorted((Identity.create() for _ in range(4)), key=lambda m: m.public_key)
    committee = Committee.create([m.public_key for m in members], 1, genesis)
    lines = []

    with tempfile.TemporaryDirectory(dir=".") as directory:
        path = Path(directory) / "votes.sqlite"
        replica = open_replica(path, committee, members[0], genesis, create=True)
        store = replica._store

        with store.group():
            for nonce in range(count):
                event = Transfer(sender.identity_id, "receiver", 1, nonce)
                votes = tuple(Vote.create(committee, member, event) for member in members[:3])
                replica.handle_certificate(QuorumCertificate(event, votes))

        root = replica.state.root()
        store.close()

        def line(mode: str) -> None:
            seconds, found = timed_open(path, committee, members[0], genesis)
            assert found == root
            lines.append(
                {
                    "certificates": count,
                    "mode": mode,
                    "restart_seconds": round(seconds, 3),
                    "store_mib": round(path.stat().st_size / 2**20, 1),
                    "peak_rss_mib": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024),
                }
            )

        line("no snapshot")
        replica = open_replica(path, committee, members[0], genesis)
        candidate = replica.candidate_snapshot()
        snapshot = Snapshot(
            candidate.epoch,
            candidate.state,
            candidate.ids,
            tuple(
                SnapshotAttestation.create(committee, member, candidate.digest, ())
                for member in members[:3]
            ),
        )
        assert replica.install_snapshot(snapshot)
        replica._store.close()
        line("snapshot")
        replica = open_replica(path, committee, members[0], genesis)
        replica.prune_covered()
        replica._store.close()
        line("snapshot and pruning")

    return lines


if __name__ == "__main__":
    for argument in sys.argv[1:]:
        for result in measure(int(argument)):
            print(json.dumps(result), flush=True)
