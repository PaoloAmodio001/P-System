"""Measure a running committee through its API: latency, throughput, recovery after a partition.

    python scripts/measure_network.py --sender-key out/sender.key \
        --api http://10.0.0.1:8080=out/node-0/api.token ... --isolate 'ssh n3 sudo sh block.sh' --heal '...'

It says nothing about where the nodes run: scripts/netem_lab.py calls it for containers with an emulated
network, and on four machines it runs the same way. It prints one line of JSON. Without --isolate
there is no measure of recovery. The last API given is the one that gets isolated.

What counts as done is the event having run on every node, read back through each API, every
`POLL_SECONDS`: so a latency has that much error, and it can be no shorter than a poll.

A measure that fails ends with code 3 and a diagnosis, as JSON on stderr and in --failure-dir if given:
for each node, whether its API answered and how far it had got, and the states compared. It cannot read
the logs of a node, since it does not know where the node runs: --collect-logs is a command that fetches
them into $PSYSTEM_FAILURE_DIR.
"""

import argparse
import http.client
import json
import os
import shutil
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
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
# A node refuses a vote further than `max_nonce_ahead` ahead of what it has run, 1024 by default. One sender
# can only have that many on their way, so this is part of what limits it, and a measure keeps under it.
MAX_ON_THEIR_WAY = 512
# How long an event may take before a measure gives up. A search for a stuck event can ask for less.
LONG_WAIT_SECONDS = float(os.environ.get("PSYSTEM_MEASURE_WAIT_SECONDS", "600"))
MEASURE_FAILED = 3

# What one node is, about one nonce. A node that does not answer has not been seen to lack the event.
API_NOT_ANSWERING = "API_NOT_ANSWERING"
API_ERROR = "API_ERROR"
EVENT_NOT_RUN = "EVENT_NOT_RUN"
EVENT_RUN = "EVENT_RUN"


class TimedOut(Exception):
    def __init__(self, message: str, diagnosis: dict | None = None) -> None:
        super().__init__(message if diagnosis is None else f"{message}: {summary_of(diagnosis)}")
        self.diagnosis = diagnosis


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


def read_metrics(client: Client) -> dict | None:
    """The numbers of /metrics, or None. The status does not say what is waiting for what."""
    headers = {} if client.token is None else {"Authorization": f"Bearer {client.token}"}
    request = urllib.request.Request(client.base_url + "/metrics", headers=headers)

    try:
        with urllib.request.urlopen(request, timeout=client.timeout, context=client._context) as answer:
            lines = answer.read().decode().splitlines()

        return {
            name: float(value)
            for name, value in (line.split() for line in lines if not line.startswith("#"))
        }
    except (OSError, ValueError, http.client.HTTPException):
        return None


def read_node(client: Client, account: str, nonce: int) -> dict:
    """
    What one node says now, and what that makes it. The account is read on both sides of the status, which
    are not one reading: a node that moved between them has a root of no use for a comparison.
    """
    reading = {"url": client.base_url}

    try:
        before = client.account(account)["next_nonce"]
        status = client.status()
        after = client.account(account)["next_nonce"]
    except ApiError as error:
        return reading | {"verdict": API_ERROR, "error": str(error)}
    except (OSError, ValueError, http.client.HTTPException) as error:
        return reading | {"verdict": API_NOT_ANSWERING, "error": repr(error)}

    return reading | {
        "verdict": EVENT_RUN if after >= nonce else EVENT_NOT_RUN,
        "next_nonce": after,
        "moving": before != after,
        "state_root": status.get("state_root"),
        "executed": status.get("executed"),
        "certificates_held": status.get("certificates_held"),
        "peers": status.get("peers"),
        "halted": status.get("halted"),
        "conflicted": status.get("conflicted"),
        "metrics": read_metrics(client),
    }


def compare_states(readings: list[dict]) -> dict:
    """
    Two roots say something only at the same point. A node behind has another root and that is no
    disagreement: so roots are compared among nodes that have run the same, and any others are left out
    and named, rather than taken as agreeing.
    """
    settled = [r for r in readings if r["verdict"] in (EVENT_RUN, EVENT_NOT_RUN) and not r["moving"]]
    points: dict[tuple, list[dict]] = {}

    for reading in settled:
        points.setdefault((reading["executed"], reading["next_nonce"]), []).append(reading)

    disagreements = [
        {
            "executed": executed,
            "next_nonce": next_nonce,
            "roots": {r["url"]: r["state_root"] for r in group},
        }
        for (executed, next_nonce), group in points.items()
        if len({r["state_root"] for r in group}) > 1
    ]
    compared = [r["url"] for group in points.values() if len(group) > 1 for r in group]
    return {
        "disagreements": disagreements,
        "compared": compared,
        "not_compared": [r["url"] for r in readings if r["url"] not in compared],
    }


def diagnose(clients: list[Client], account: str, nonce: int) -> dict:
    """What the nodes say about `account` and `nonce`. Only reads, and whatever they answer it returns."""
    readings = [read_node(client, account, nonce) for client in clients]
    return {
        "account": account,
        "nonce": nonce,
        "nodes": readings,
        "states": compare_states(readings),
    }


def summary_of(diagnosis: dict) -> str:
    verdicts = [node["verdict"] for node in diagnosis["nodes"]]
    parts = [f"{verdicts.count(verdict)} {verdict}" for verdict in sorted(set(verdicts))]

    if diagnosis["states"]["disagreements"]:
        parts.append("STATE ROOTS DIFFER AT THE SAME POINT")

    return ", ".join(parts)


@dataclass
class Watch:
    """What one node said while it was waited for: a last answer alone cannot tell a stop from a blink."""

    polls: int = 0
    unanswered: int = 0
    last_nonce: int | None = None
    last_answer: float | None = None
    last_progress: float | None = None

    def see(self, nonce: int | None) -> int | None:
        now = time.monotonic()
        self.polls += 1

        if nonce is None:
            self.unanswered += 1
            return None

        self.last_answer = now

        if nonce != self.last_nonce:
            self.last_progress = now

        self.last_nonce = nonce
        return nonce

    def report(self) -> dict:
        now = time.monotonic()
        return {
            "polls": self.polls,
            "unanswered": self.unanswered,
            "last_nonce": self.last_nonce,
            "seconds_since_answer": None if self.last_answer is None else round(now - self.last_answer, 2),
            "seconds_since_progress": None if self.last_progress is None else round(now - self.last_progress, 2),
        }


def wait_for(clients: list[Client], account: str, nonce: int, seconds: float) -> float:
    """Until every one of `clients` has run up to `nonce`. Returns the seconds that took."""
    started = time.monotonic()
    pending = list(clients)
    watches = {client: Watch() for client in clients}

    while pending:
        pending = [c for c in pending if (watches[c].see(next_nonce_of(c, account)) or 0) < nonce]

        if not pending:
            break

        if time.monotonic() - started > seconds:
            diagnosis = diagnose(clients, account, nonce)

            for client, node in zip(clients, diagnosis["nodes"]):
                node["while_waiting"] = watches[client].report()

            raise TimedOut(f"{len(pending)} NODES NOT AT NONCE {nonce}", diagnosis)

        time.sleep(POLL_SECONDS)

    return time.monotonic() - started


def wait_connected(clients: list[Client], seconds: float = 60.0) -> None:
    """
    Every node sees every other. An event sent before that reaches too few to get a certificate, and
    nothing sends it again by itself, so a measure would only wait. Seeing each other now does not say
    that these connections will stay: see scripts/probe_stuck_event.py.
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


def send_paced(clients: list[Client], account: str, events: list[SignedTransfer]) -> None:
    """In batches, with at most `MAX_ON_THEIR_WAY` not yet run on the slowest of `clients`."""
    for start in range(0, len(events), BATCH):
        batch = events[start:start + BATCH]
        allowed = batch[-1].transfer.nonce + 1 - MAX_ON_THEIR_WAY

        if allowed > 0:
            wait_for(clients, account, allowed, LONG_WAIT_SECONDS)

        clients[0].submit_many(batch)


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

    send_paced(clients, sender.identity.identity_id, events)
    wait_for(clients, sender.identity.identity_id, sender.next_nonce, LONG_WAIT_SECONDS)
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

        send_paced(majority, account, events)
        wait_for(majority, account, sender.next_nonce, LONG_WAIT_SECONDS)

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
    wait_for([clients[-1]], account, sender.next_nonce, LONG_WAIT_SECONDS)
    caught_up = time.monotonic() - started
    deadline = time.monotonic() + 60.0

    while clients[-1].status()["state_root"] != clients[0].status()["state_root"]:
        if time.monotonic() > deadline:
            raise TimedOut("STATE ROOTS DIFFER AFTER RECOVERY", diagnose(clients, account, sender.next_nonce))

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


def save_failure(
    directory: Path,
    error: BaseException,
    diagnosis: dict,
    logs: list[Path] = (),
    collect_logs: str | None = None,
) -> dict:
    """
    Keep what a failed measure leaves. Nothing here may hide the failure itself: a log that cannot be had
    is written down, and the rest is kept. Returns what was written to diagnosis.json.
    """
    directory.mkdir(parents=True, exist_ok=True)
    report = {"error": repr(error), "at_the_end": diagnosis, "logs_missing": []}
    waited = getattr(error, "diagnosis", None)

    if waited is not None:
        report["when_it_gave_up"] = waited

    for log in logs:
        try:
            shutil.copy(log, directory / f"{log.parent.name}-{log.name}")
        except OSError as problem:
            report["logs_missing"].append({"log": str(log), "reason": repr(problem)})

    if collect_logs is not None:
        try:
            subprocess.run(
                collect_logs,
                shell=True,
                check=True,
                capture_output=True,
                timeout=300,
                env={**os.environ, "PSYSTEM_FAILURE_DIR": str(directory)},
            )
        except (OSError, subprocess.SubprocessError) as problem:
            report["logs_missing"].append({"log": collect_logs, "reason": repr(problem)})

    (directory / "diagnosis.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


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
    parser.add_argument("--failure-dir", type=Path, help="where a failed measure keeps its diagnosis")
    parser.add_argument("--node-log", type=Path, action="append", default=[], help="a log to keep, if it is here")
    parser.add_argument("--collect-logs", help="a command that puts the logs in $PSYSTEM_FAILURE_DIR")
    options = parser.parse_args()
    sender = Sender(Identity.load(options.sender_key))
    clients = [make_client(entry) for entry in options.api]
    account = sender.identity.identity_id

    def failed(error: Exception) -> int:
        diagnosis = diagnose(clients, account, sender.next_nonce)
        report = {"error": repr(error), "at_the_end": diagnosis}

        if options.failure_dir is not None:
            report = save_failure(options.failure_dir, error, diagnosis, options.node_log, options.collect_logs)

        print(json.dumps(report), file=sys.stderr)
        return MEASURE_FAILED

    try:
        sender.next_nonce = clients[0].account(account)["next_nonce"]
        results = measure_all(
            clients,
            sender,
            options.latency_events,
            options.throughput_events,
            options.recovery_events,
            (lambda: run_shell(options.isolate)) if options.isolate else None,
            (lambda: run_shell(options.heal)) if options.heal else None,
        )
    except (TimedOut, IsolationFailed, ApiError, OSError, ValueError, subprocess.SubprocessError) as error:
        return failed(error)

    print(json.dumps(results))

    if not results["same_state_on_all"]:
        # Measured and printed, and worth keeping: nothing else would say which node differs.
        failed(ValueError("STATE ROOTS DIFFER AT THE END OF THE MEASURE"))
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
