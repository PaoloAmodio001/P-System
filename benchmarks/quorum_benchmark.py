"""Measure quorum mode: the costs one by one, then four to thirteen nodes on real TLS.

    python benchmarks/quorum_benchmark.py --dir /a/real/disk --out results.json

The numbers belong to the machine and the moment of the run. A run on tmpfs measures no fsync, so
pass a directory on the disk you mean to measure. Nothing here is compared with another system.
"""

import argparse
import cProfile
import io
import itertools
import json
import os
import platform
import pstats
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.attestation import Committee, QuorumCertificate, Vote  # noqa: E402
from core.event import Transfer  # noqa: E402
from core.signed_event import SignedTransfer  # noqa: E402
from core.state import State  # noqa: E402
from crypto.identity import Identity  # noqa: E402
from network.message import encode_certificate, encode_vote_request  # noqa: E402
from network.node import Node  # noqa: E402
from network.peer import Peer  # noqa: E402
from network.quorum import (  # noqa: E402
    QuorumConfig,
    QuorumDriver,
    QuorumReplica,
    SqliteVoteStore,
)


def committee_of(f: int, senders: int = 1, balance: int = 10**9):
    members = sorted(
        (Identity.create() for _ in range(3 * f + 1)),
        key=lambda member: member.public_key,
    )
    people = [Identity.create() for _ in range(senders)]
    genesis = State({person.identity_id: balance for person in people})
    committee = Committee.create([m.public_key for m in members], f, genesis)
    return members, people, genesis, committee


def rate(count: int, seconds: float) -> float:
    return round(count / seconds, 1)


def measure_signatures(count: int = 2000) -> dict:
    identity = Identity.create()
    event = Transfer("alice", "bob", 1, 0)
    started = time.perf_counter()
    for _ in range(count):
        signed = SignedTransfer.create(identity, event)
    sign = time.perf_counter() - started
    started = time.perf_counter()
    for _ in range(count):
        signed.verify()
    verify = time.perf_counter() - started
    return {"ed25519_sign_per_s": rate(count, sign), "ed25519_verify_per_s": rate(count, verify)}


def measure_durable_votes(directory: Path, count: int = 500) -> dict:
    members, people, _genesis, committee = committee_of(1)
    store = SqliteVoteStore(directory / "votes.sqlite", committee, members[0].public_key, create=True)
    events = [Transfer(people[0].identity_id, "bob", 1, nonce) for nonce in range(count)]
    started = time.perf_counter()
    for event in events:
        store.record_vote(event)
    elapsed = time.perf_counter() - started
    store.close()
    return {"durable_votes_per_s": rate(count, elapsed), "durable_vote_ms": round(1000 * elapsed / count, 3)}


def measure_certificates(f: int, count: int = 300) -> dict:
    members, people, _genesis, committee = committee_of(f)
    event = Transfer(people[0].identity_id, "bob", 1, 0)
    votes = tuple(Vote.create(committee, members[i], event) for i in range(committee.quorum))
    certificate = QuorumCertificate(event, votes)
    started = time.perf_counter()
    for _ in range(count):
        assert certificate.verify(committee)
    elapsed = time.perf_counter() - started
    return {
        "f": f,
        "n": committee.n,
        "certificate_verify_per_s": rate(count, elapsed),
        "certificate_bytes": len(json.dumps(encode_certificate(certificate))),
    }


def _replica(directory: Path, member, committee, genesis, name: str):
    store = SqliteVoteStore(directory / f"{name}.sqlite", committee, member.public_key, create=True)
    return store, QuorumDriver(QuorumReplica(member, genesis, store, lambda _event: True))


def measure_replica_path(directory: Path, count: int = 300, profile: bool = False) -> dict:
    """One node, no network: asking for a vote, then executing the certificate."""
    members, people, genesis, committee = committee_of(1)
    store, driver = _replica(directory, members[0], committee, genesis, "path")
    sender = people[0]
    signed = [
        SignedTransfer.create(sender, Transfer(sender.identity_id, "bob", 1, nonce))
        for nonce in range(count)
    ]
    requests = [encode_vote_request(item) for item in signed]
    certificates = [
        encode_certificate(
            QuorumCertificate(
                item.transfer,
                tuple(Vote.create(committee, members[i], item.transfer) for i in range(3)),
            )
        )
        for item in signed
    ]
    profiler = cProfile.Profile() if profile else None
    if profiler:
        profiler.enable()
    started = time.perf_counter()
    for message in requests:
        driver.handle_message(message)
    votes = time.perf_counter() - started
    started = time.perf_counter()
    for message in certificates:
        driver.handle_message(message)
    executed = time.perf_counter() - started
    if profiler:
        profiler.disable()
    assert len(driver.replica.executed) == count
    store.close()
    result = {
        "vote_requests_per_s": rate(count, votes),
        "certificates_executed_per_s": rate(count, executed),
    }
    if profiler:
        out = io.StringIO()
        pstats.Stats(profiler, stream=out).sort_stats("tottime").print_stats(12)
        result["profile"] = out.getvalue().splitlines()[4:]
    return result


def wait_until(condition, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.002)
    return condition()


def workload_events(people: list[Identity], count: int) -> list[SignedTransfer]:
    """Create a deterministic round-robin workload with an independent nonce stream per sender."""
    if not people:
        raise ValueError("at least one sender is required")
    if count < 1:
        raise ValueError("count must be positive")

    nonces = [0] * len(people)
    events = []
    for index in range(count):
        sender_index = index % len(people)
        sender = people[sender_index]
        events.append(
            SignedTransfer.create(
                sender,
                Transfer(sender.identity_id, "bob", 1, nonces[sender_index]),
            )
        )
        nonces[sender_index] += 1
    return events


def measure_network(
    directory: Path,
    f: int,
    count: int,
    sequential: bool,
    batch: int = 1,
    senders: int = 1,
) -> dict:
    """
    Real nodes on real TLS, on one machine. Sequential mode gives latency, while batches and
    multiple sender streams measure throughput under a bounded workload. All nodes run in this
    one process, so they share one interpreter: that is a floor, and separate machines would not
    have that limit.
    """
    members, people, genesis, committee = committee_of(f, senders)
    tag = os.urandom(3).hex()
    nodes = [
        Node(
            f"bench-{tag}-{index}",
            genesis,
            quorum=QuorumConfig(
                committee,
                member,
                directory / f"{tag}-{index}.sqlite",
                create=True,
                sync_interval=None,
            ),
        )
        for index, member in enumerate(members)
    ]
    for node in nodes:
        node.start()
    try:
        for low, high in itertools.combinations(nodes, 2):
            host, port = high.address()
            low.connect_peer(Peer(node_id=high.node_id, host=host, port=port))
        assert wait_until(lambda: all(len(n.peer_connections) == len(nodes) - 1 for n in nodes), 30)
        signed = workload_events(people, count)
        expected_ids = {item.transfer.event_id() for item in signed}
        latencies = []
        started = time.perf_counter()
        if sequential:
            for item in signed:
                before = time.perf_counter()
                assert nodes[0].submit(item)
                event_id = item.transfer.event_id()
                assert wait_until(
                    lambda: all(
                        event_id in {event.transfer.event_id() for event in n.local_events}
                        for n in nodes
                    ),
                    30,
                )
                latencies.append(time.perf_counter() - before)
        else:
            for start in range(0, count, batch):
                assert nodes[0].submit_many(signed[start:start + batch])
        assert wait_until(
            lambda: all(expected_ids <= {event.transfer.event_id() for event in n.local_events} for n in nodes),
            120,
        )
        elapsed = time.perf_counter() - started
    finally:
        for node in nodes:
            node.stop()
    result = {
        "f": f,
        "n": committee.n,
        "events": count,
        "batch": batch,
        "senders": senders,
        "executed_on_all_per_s": rate(count, elapsed),
        "events_per_sender": {person.identity_id: sum(item.transfer.sender == person.identity_id for item in signed) for person in people},
        "state_roots": [node.state.root() for node in nodes],
        "event_counts": [len(node.local_events) for node in nodes],
    }
    if latencies:
        result["latency_ms_median"] = round(1000 * statistics.median(latencies), 1)
        result["latency_ms_p95"] = round(1000 * statistics.quantiles(latencies, n=20)[18], 1) if len(latencies) >= 2 else result["latency_ms_median"]
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dir", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--senders", type=int, default=1)
    args = parser.parse_args()
    if args.senders < 1:
        parser.error("--senders must be positive")
    base = tempfile.TemporaryDirectory(dir=args.dir)
    directory = Path(base.name)
    scale = 1 if not args.quick else 0.1
    results = {
        "machine": {
            "python": platform.python_version(),
            "system": platform.platform(),
            "processor": platform.processor(),
            "cpus": os.cpu_count(),
            "directory": str(args.dir),
        },
        "signatures": measure_signatures(int(2000 * scale)),
        "durable_votes": measure_durable_votes(directory, int(500 * scale)),
        "certificates": [measure_certificates(f, int(300 * scale)) for f in (1, 2, 3, 4)],
        "replica_path": measure_replica_path(directory, int(300 * scale), args.profile),
        "network_latency": [
            measure_network(directory, f, max(int(60 * scale), 5), sequential=True, senders=args.senders)
            for f in (1, 2, 4)
        ],
        "network_throughput": [
            measure_network(directory, f, max(int(600 * scale), 10), False, batch, args.senders)
            for f in (1, 2, 4)
            for batch in (1, 50)
        ],
    }
    text = json.dumps(results, indent=2)
    print(text)
    if args.out:
        args.out.write_text(text + "\n")
    base.cleanup()


if __name__ == "__main__":
    main()
