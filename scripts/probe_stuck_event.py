"""Look for what leaves an event stuck, on real processes. It proves nothing about any one failure.

    python scripts/probe_stuck_event.py cut --links 2 --runs 8     connections of the first node cut in a burst
    python scripts/probe_stuck_event.py resend --runs 4            the same, then the same events sent again
    python scripts/probe_stuck_event.py links --runs 15            connections that end, with no fault, after
                                                                   the nodes say they see each other
    python scripts/probe_stuck_event.py burst --runs 25 --pause 0  a burst with no fault, after a pause

It prints one line of JSON for each run and one to end. What it found is in the docstring of tests/test_stuck_event.py.
"""

import argparse
import json
import random
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crypto.identity import Identity  # noqa: E402
from scripts import measure_network as measure  # noqa: E402
from sdk.client import Client  # noqa: E402
from tests.chaos import ChaosDeployment  # noqa: E402
from tests.deployment_helpers import Deployment, stop_leftovers  # noqa: E402
from tests.failure_evidence import compare_stores, read_store  # noqa: E402

BURST = 50
ESTABLISHED = "01"
# Longer than a node may wait for the other side of a dial, so that only what the probe does acts.
SETTLE_SECONDS = 4.0
LINKS_WATCH_SECONDS = 8.0


def established_links(ports: set[int], table: Path = Path("/proc/net/tcp")) -> set[frozenset[int]]:
    """The TCP connections with one end on `ports`, each as its two ports. Linux, and IPv4 only."""
    links = set()

    for line in table.read_text().splitlines()[1:]:
        fields = line.split()

        if fields[3] != ESTABLISHED:
            continue

        local, remote = (int(fields[i].split(":")[1], 16) for i in (1, 2))

        if local in ports or remote in ports:
            links.add(frozenset((local, remote)))

    return links


def started(made) -> list[Client]:
    made.start_all()
    clients = [Client(made.api_url(index)) for index in range(made.count)]
    measure.wait_connected(clients)
    return clients


def where_it_stopped(made, diagnosis: dict) -> dict:
    account, nonce = diagnosis["account"], diagnosis["nonce"]
    stores = {made.node_id(i): read_store(made.store(i), account) for i in range(made.count)}
    compared = compare_stores(stores, nonce)
    return {
        "next_nonces": [node.get("next_nonce") for node in diagnosis["nodes"]],
        "verdicts": [node["verdict"] for node in diagnosis["nodes"]],
        "peers": [len(node.get("peers") or []) for node in diagnosis["nodes"]],
        "disagreements": diagnosis["states"]["disagreements"],
        "voted_by_none": compared["voted_by_none"][:5],
        "first_not_certified": compared["not_certified_everywhere"][:2],
    }


def burst_with_cuts(made, clients, rng, links: int, wait: float) -> tuple[measure.Sender, list, dict | None]:
    """The events of a burst, with `links` connections of the first node cut while they leave."""
    time.sleep(SETTLE_SECONDS)
    sender = measure.Sender(Identity.load(made.sender_key))
    events = [sender.next() for _ in range(BURST)]
    chosen = rng.sample(range(1, made.count), links)

    def cut() -> None:
        time.sleep(rng.uniform(0, 0.03))

        for peer in chosen:
            made.links[(0, peer)].cut()

    thread = threading.Thread(target=cut)
    thread.start()
    clients[0].submit_many(events)
    thread.join()

    try:
        measure.wait_for(clients, sender.identity.identity_id, BURST, wait)
    except measure.TimedOut as error:
        return sender, events, error.diagnosis

    return sender, events, None


def cut_run(base: Path, run: int, options) -> dict:
    rng = random.Random(1000 * options.links + run)
    made = ChaosDeployment(base, rng)

    try:
        clients = started(made)
        _, _, diagnosis = burst_with_cuts(made, clients, rng, options.links, options.wait)

        if diagnosis is None:
            return {"stuck": False}

        # After the wait, the nodes have had many rounds of synchronization to help themselves.
        time.sleep(options.wait / 2)
        later = [measure.next_nonce_of(client, diagnosis["account"]) for client in clients]
        return {"stuck": True, "next_nonces_later": later, **where_it_stopped(made, diagnosis)}
    finally:
        made.close()


def resend_run(base: Path, run: int, options) -> dict:
    rng = random.Random(run)
    made = ChaosDeployment(base, rng)

    try:
        clients = started(made)
        sender, events, diagnosis = burst_with_cuts(made, clients, rng, 2, options.wait)

        if diagnosis is None:
            return {"stuck": False}

        clients[0].submit_many(events)

        try:
            seconds = measure.wait_for(clients, sender.identity.identity_id, BURST, options.wait)
            return {"stuck": True, "freed_after_seconds": round(seconds, 2)}
        except measure.TimedOut:
            return {"stuck": True, "freed_after_seconds": None}
    finally:
        made.close()


def links_run(base: Path, run: int, options) -> dict:
    made = Deployment(base)

    try:
        started(made)
        began = time.monotonic()
        ports = set(made.ports)
        first = established_links(ports)
        ended: dict[frozenset, float] = {}

        while time.monotonic() - began < LINKS_WATCH_SECONDS:
            for link in first - established_links(ports):
                ended.setdefault(link, round(time.monotonic() - began, 2))

            time.sleep(0.01)

        return {"links": len(first), "ended": len(ended), "after_seconds": sorted(ended.values())}
    finally:
        made.stop_all()


def burst_run(base: Path, run: int, options) -> dict:
    made = Deployment(base)

    try:
        clients = started(made)
        time.sleep(options.pause)
        sender = measure.Sender(Identity.load(made.sender_key))
        clients[0].submit_many([sender.next() for _ in range(BURST)])

        try:
            measure.wait_for(clients, sender.identity.identity_id, BURST, options.wait)
            return {"stuck": False}
        except measure.TimedOut as error:
            return {"stuck": True, **where_it_stopped(made, error.diagnosis)}
    finally:
        made.stop_all()


RUNS = {"cut": cut_run, "resend": resend_run, "links": links_run, "burst": burst_run}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("what", choices=sorted(RUNS))
    parser.add_argument("--runs", type=int, default=8)
    parser.add_argument("--links", type=int, default=2)
    parser.add_argument("--pause", type=float, default=0.0)
    parser.add_argument("--wait", type=float, default=60.0)
    options = parser.parse_args()
    results = []

    for run in range(options.runs):
        with tempfile.TemporaryDirectory() as base:
            try:
                result = RUNS[options.what](Path(base), run, options)
            finally:
                stop_leftovers()

        results.append(result)
        print(json.dumps({"run": run, **result}), flush=True)

    print(json.dumps({"runs": len(results), "stuck": sum(r.get("stuck", False) for r in results)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
