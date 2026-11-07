"""What a test on real processes leaves behind when it fails.

pytest deletes old temporary directories, and a CI machine takes everything with it: so a failure is copied
to `test-failures/`, or to $PSYSTEM_FAILURE_DIR, and the part that matters is printed, to be in the report of
pytest and so in the log of the CI. The logs of a node say little about messages. The stores say the rest:
who voted for each nonce and who holds a certificate, which is where a stuck event stopped.
"""

import json
import os
import signal
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from scripts.measure_network import diagnose, save_failure, summary_of

ROOT = Path(__file__).resolve().parent.parent
LOG_LINES_PRINTED = 120
STORE_ROWS_PRINTED = 8
SECONDS_BETWEEN_DUMPS = 2.0


def failures_directory(name: str) -> Path:
    base = Path(os.environ.get("PSYSTEM_FAILURE_DIR", ROOT / "test-failures"))
    return base / f"{name}-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"


def copy_store(source: Path, target: Path) -> None:
    """Through SQLite, and read-only: a node may still be writing, and a plain copy could be torn."""
    with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as reading:
        with sqlite3.connect(target) as writing:
            reading.backup(writing)


def read_store(path: Path, account: str) -> dict:
    """For `account`, by nonce, the event this node voted for and the one it holds a certificate of."""
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as store:
        voted = {
            int(nonce): event_id
            for nonce, event_id in store.execute(
                "SELECT nonce, event_id FROM votes WHERE sender = ?", (account,)
            )
        }
        certified = {}

        for event_id, canonical in store.execute("SELECT event_id, canonical FROM certificates"):
            event = json.loads(canonical)

            if event["sender"] == account:
                certified[int(event["nonce"])] = event_id

    return {"voted": voted, "certified": certified}


def compare_stores(stores: dict[str, dict], up_to: int) -> dict:
    """
    Where the nodes stopped, nonce by nonce, from the first that some node has no certificate of. A nonce
    with one voter stopped before the request reached anyone; with a quorum of voters and no certificate, the
    votes did not come back; with a certificate on some, it did not spread. A nonce under `up_to` that no node
    voted for never started, not even on the node it was sent to. Two events for one nonce is something
    else, and it is said apart.
    """
    nonces = sorted({n for store in stores.values() for part in store.values() for n in part})
    rows = []
    different = []

    for nonce in nonces:
        voted_by = [name for name, store in stores.items() if nonce in store["voted"]]
        certified_by = [name for name, store in stores.items() if nonce in store["certified"]]
        events = {store[part][nonce] for store in stores.values() for part in store if nonce in store[part]}

        if len(events) > 1:
            different.append(nonce)

        if len(certified_by) < len(stores):
            rows.append({"nonce": nonce, "voted_by": voted_by, "certified_by": certified_by})

    return {
        "voted_by_none": [nonce for nonce in range(up_to) if not any(nonce in s["voted"] for s in stores.values())],
        "highest_nonce_seen": nonces[-1] if nonces else None,
        "different_events_for_a_nonce": different,
        "not_certified_everywhere": rows,
    }


def process_states(made) -> dict:
    states = {}

    for index in range(made.count):
        process = made.processes.get(index)
        code = None if process is None else process.poll()
        states[made.node_id(index)] = (
            "not running: stopped by the test" if process is None
            else "running" if code is None
            else f"exited with {code}"
        )

    return states


def dump_threads(made, times: int = 2) -> None:
    """Into each log, with the signal the node handles for this. Twice: a thread that has not moved is stuck."""
    for turn in range(times):
        if turn:
            time.sleep(SECONDS_BETWEEN_DUMPS)

        for process in made.processes.values():
            if process.poll() is None:
                process.send_signal(signal.SIGUSR1)

    time.sleep(0.2)


def tail(path: Path, lines: int) -> str:
    return "\n".join(path.read_text(errors="replace").splitlines()[-lines:])


def save_evidence(made, clients, account: str, nonce: int, error: BaseException, name: str) -> Path:
    directory = failures_directory(name)
    directory.mkdir(parents=True)
    # In this order: the API first, since a dump of threads takes a moment of a node that may be slow.
    diagnosis = diagnose(clients, account, nonce)
    processes = process_states(made)
    dump_threads(made)
    logs = [made.directory(index) / "node.log" for index in range(made.count)]
    report = save_failure(directory, error, diagnosis, logs)
    stores = {}

    for index in range(made.count):
        node = made.node_id(index)

        try:
            copy_store(made.store(index), directory / f"{node}-votes.sqlite")
            stores[node] = read_store(directory / f"{node}-votes.sqlite", account)
        except sqlite3.Error as problem:
            report["logs_missing"].append({"log": f"store of {node}", "reason": repr(problem)})

    compared = compare_stores(stores, nonce)
    report |= {"processes": processes, "stores": compared}
    (directory / "diagnosis.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"\n=== EVIDENCE OF THIS FAILURE IS IN {directory}")
    print(f"=== NODES: {summary_of(diagnosis)}")
    print(f"=== PROCESSES: {json.dumps(processes)}")
    print(f"=== WHEN IT GAVE UP: {json.dumps(report.get('when_it_gave_up'))}")
    print(f"=== AT THE END: {json.dumps(diagnosis)}")
    shown = compared | {"not_certified_everywhere": compared["not_certified_everywhere"][:STORE_ROWS_PRINTED]}
    print(f"=== STORES: {json.dumps(shown)}")

    for log in logs:
        print(f"=== LOG OF {log.parent.name}\n{tail(log, LOG_LINES_PRINTED)}")

    return directory


@contextmanager
def evidence_on_failure(made, clients, account: str, nonce, name: str):
    """`nonce` is called when it fails. The failure goes on as it was, whatever happens here."""
    try:
        yield
    except Exception as error:
        try:
            save_evidence(made, clients, account, nonce(), error, name)
        except Exception as problem:  # A diagnosis that fails must not hide what it was for.
            print(f"=== EVIDENCE WAS NOT SAVED: {problem!r}")

        raise
