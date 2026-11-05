"""Measure a running committee through its API: latency, throughput, recovery after a partition.

    python scripts/measure_network.py --sender-key out/sender.key \
        --api http://10.0.0.1:8080=out/node-0/api.token ... --isolate 'ssh n3 sudo sh block.sh' --heal '...'

It says nothing about where the nodes run: scripts/netem_lab.py calls it for containers with an emulated
network, and on four machines it runs the same way. It prints one line of JSON. Without --isolate
there is no measure of recovery. The last API given is the one that gets isolated.

What counts as done is the event having run on every node, read back through each API, every
`POLL_SECONDS`: so a latency has that much error, and it can be no shorter than a poll.
"""

import argparse
import json
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.event import Transfer  # noqa: E402
from core.signed_event import SignedTransfer  # noqa: E402
from crypto.identity import Identity  # noqa: E402
from sdk.client import ApiError, Client  # noqa: E402

POLL_SECONDS = 0.01
BATCH = 64
ISOLATION_CHECK_SECONDS = 2.0


class TimedOut(Exception):
    pass


class IsolationFailed(Exception):
    pass


@dataclass
class Sender:
    """Signs in sequence, and remembers where it is, through every measure."""

    identity: Identity
    next_nonce: int = 0

    def next(self) -> SignedTransfer:
        signed = SignedTransfer.create(
            self.identity,
            Transfer(self.identity.identity_id, "receiver", 1, self.next_nonce),
        )
        self.next_nonce += 1
        return signed


def next_nonce_of(client: Client, account: str) -> int | None:
    """None if this node cannot answer now, which is what a partition looks like."""
    try:
        return client.account(account)["next_nonce"]
    except (ApiError, OSError):
        return None


def wait_for(clients: list[Client], account: str, nonce: int, seconds: float) -> float:
    """Until every one of `clients` has run up to `nonce`. Returns the seconds that took."""
    started = time.monotonic()
    pending = list(clients)

    while pending:
        pending = [c for c in pending if (next_nonce_of(c, account) or 0) < nonce]

        if not pending:
            break

        if time.monotonic() - started > seconds:
            raise TimedOut(f"{len(pending)} NODES NOT AT NONCE {nonce}")

        time.sleep(POLL_SECONDS)

    return time.monotonic() - started


def wait_connected(clients: list[Client], seconds: float = 60.0) -> None:
    """
    Every node sees every other. An event sent before that reaches too few to get a certificate, and
    nothing sends it again by itself, so a measure would only wait.
    """
    deadline = time.monotonic() + seconds

    while True:
        try:
            if all(len(client.status()["peers"]) >= len(clients) - 1 for client in clients):
                return
        except (ApiError, OSError):
            pass

        if time.monotonic() > deadline:
            raise TimedOut("THE NODES DO NOT SEE EACH OTHER")

        time.sleep(0.1)


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * fraction))]


def measure_latency(clients: list[Client], sender: Sender, count: int) -> dict:
    """One event at a time: sent to the first node, done when on all."""
    latencies = []

    for _ in range(count):
        signed = sender.next()
        started = time.monotonic()
        clients[0].submit(signed)
        wait_for(clients, sender.identity.identity_id, sender.next_nonce, 60.0)
        latencies.append(time.monotonic() - started)

    return {
        "events": count,
        "median_ms": round(statistics.median(latencies) * 1000, 1),
        "p95_ms": round(percentile(latencies, 0.95) * 1000, 1),
    }


def measure_throughput(clients: list[Client], sender: Sender, count: int) -> dict:
    """All of them, in batches, as fast as they are taken. Done when all have run on all nodes."""
    events = [sender.next() for _ in range(count)]
    started = time.monotonic()

    for start in range(0, count, BATCH):
        clients[0].submit_many(events[start:start + BATCH])

    wait_for(clients, sender.identity.identity_id, sender.next_nonce, 600.0)
    seconds = time.monotonic() - started
    return {
        "events": count,
        "seconds": round(seconds, 2),
        "events_per_second": round(count / seconds, 1),
    }


def run_shell(command: str) -> None:
    subprocess.run(command, shell=True, check=True, capture_output=True)


def measure_recovery(
    clients: list[Client],
    sender: Sender,
    count: int,
    isolate,
    heal,
) -> dict:
    """
    The last node is cut off. The others go on, since they are a quorum. Done when it has caught up and
    has the same state root as the first.
    """
    account = sender.identity.identity_id
    majority = clients[:-1]
    isolate()

    try:
        events = [sender.next() for _ in range(count)]

        for start in range(0, count, BATCH):
            majority[0].submit_many(events[start:start + BATCH])

        wait_for(majority, account, sender.next_nonce, 600.0)

        # If it gets them all the same, nothing was cut off, and a number here would be a lie. It may
        # be a moment behind the others, so it has that moment.
        deadline = time.monotonic() + ISOLATION_CHECK_SECONDS

        while time.monotonic() < deadline:
            if (next_nonce_of(clients[-1], account) or 0) >= sender.next_nonce:
                raise IsolationFailed("THE ISOLATED NODE STILL GOT EVERY EVENT")

            time.sleep(POLL_SECONDS)
    finally:
        heal()

    started = time.monotonic()
    wait_for([clients[-1]], account, sender.next_nonce, 600.0)
    caught_up = time.monotonic() - started
    deadline = time.monotonic() + 60.0

    while clients[-1].status()["state_root"] != clients[0].status()["state_root"]:
        if time.monotonic() > deadline:
            raise TimedOut("STATE ROOTS DIFFER AFTER RECOVERY")

        time.sleep(POLL_SECONDS)

    return {"events_missed": count, "seconds_to_catch_up": round(caught_up, 2)}


def measure_all(
    clients: list[Client],
    sender: Sender,
    latency_events: int,
    throughput_events: int,
    recovery_events: int,
    isolate=None,
    heal=None,
) -> dict:
    wait_connected(clients)
    results = {
        "latency": measure_latency(clients, sender, latency_events),
        "throughput": measure_throughput(clients, sender, throughput_events),
    }

    if isolate is not None:
        results["recovery"] = measure_recovery(clients, sender, recovery_events, isolate, heal)

    roots = {client.status()["state_root"] for client in clients}
    results["same_state_on_all"] = len(roots) == 1
    return results


def make_client(entry: str) -> Client:
    url, token_file = entry.split("=", 1)
    return Client(url, token=Path(token_file).read_text().strip())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sender-key", type=Path, required=True)
    parser.add_argument("--api", action="append", required=True, help="url=token_file, once for each node")
    parser.add_argument("--latency-events", type=int, default=100)
    parser.add_argument("--throughput-events", type=int, default=2000)
    parser.add_argument("--recovery-events", type=int, default=1000)
    parser.add_argument("--isolate")
    parser.add_argument("--heal")
    options = parser.parse_args()
    sender = Sender(Identity.load(options.sender_key))
    clients = [make_client(entry) for entry in options.api]
    sender.next_nonce = clients[0].account(sender.identity.identity_id)["next_nonce"]
    results = measure_all(
        clients,
        sender,
        options.latency_events,
        options.throughput_events,
        options.recovery_events,
        (lambda: run_shell(options.isolate)) if options.isolate else None,
        (lambda: run_shell(options.heal)) if options.heal else None,
    )
    print(json.dumps(results))
    return 0 if results["same_state_on_all"] else 1


if __name__ == "__main__":
    sys.exit(main())
