"""The files for nodes on separate machines, and the measure, on four real processes.

Docker and four machines cannot run here in the suite: they ran by hand, and docs/BENCHMARKS.md says
when and what. What can run here is that the files are what a node reads, that the commands of the lab
are what they should be, and that a measure says what really happened, on real processes.
"""

import json
import os
import signal
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from core.event import Transfer
from crypto.identity import Identity
from network.deployment import read_genesis, read_node_config
from scripts import make_host_deployment as hosts_module
from scripts import measure_network as measure_module
from scripts import netem_lab as lab
from sdk.client import Client
from tests import failure_evidence as evidence
from tests.deployment_helpers import Deployment, wait_until

HOSTS = {f"node-{i}": f"10.0.0.{i + 1}" for i in range(4)}


@pytest.fixture(scope="module")
def deployment(tmp_path_factory):
    base = tmp_path_factory.mktemp("hosts") / "out"
    info = hosts_module.write_deployment(base, HOSTS, 7100, 8100, snapshot_every=50)
    return base, info


def test_each_node_reads_its_own_configuration(deployment):
    base, _ = deployment

    for name, address in HOSTS.items():
        config = read_node_config(base / name / "node.toml")
        assert config.node_id == name
        assert config.port == 7100
        assert config.api.port == 8100
        assert config.snapshot_every == 50
        assert {peer.node_id: peer.host for peer in config.peers} == {
            other: where for other, where in HOSTS.items() if other != name
        }
        assert all(peer.port == 7100 for peer in config.peers)


def test_every_member_is_in_the_genesis_with_a_quorum(deployment):
    base, info = deployment
    genesis = read_genesis(base / "genesis.json")
    assert genesis.committee.n == 4
    assert genesis.committee.quorum == 3
    assert genesis.state.balance(info["sender"]) == 10**9
    assert info["names"] == list(HOSTS)


def test_a_store_is_ready_on_each_and_a_token_is_private(deployment):
    base, _ = deployment

    for name in HOSTS:
        assert (base / name / "votes.sqlite").exists()
        assert (base / name / "api.token").stat().st_mode & 0o777 == 0o600


def test_tokens_differ(deployment):
    base, _ = deployment
    assert len({(base / name / "api.token").read_text() for name in HOSTS}) == 4


@pytest.mark.parametrize("count", [1, 2, 3, 5, 6])
def test_only_a_committee_of_3f_plus_1_with_a_fault_to_tolerate(tmp_path, count):
    hosts = {f"n{i}": "10.0.0.1" for i in range(count)}
    with pytest.raises(ValueError):
        hosts_module.write_deployment(tmp_path / "x", hosts)
    assert not (tmp_path / "x").exists()


def test_no_snapshots_unless_asked():
    assert "[snapshots]" not in hosts_module.node_config("a", {"a": "1", "b": "2"}, 1, 2)
    assert "every = 9" in hosts_module.node_config("a", {"a": "1"}, 1, 2, snapshot_every=9)


def test_a_node_is_not_its_own_peer():
    text = hosts_module.node_config("a", {"a": "1", "b": "2"}, 1, 2)
    assert 'node_id = "b"' in text
    assert text.count("[[peers]]") == 1


# --- The lab --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "delay,jitter,loss,expected",
    [
        (0, 0, 0, ["netem"]),
        (25, 0, 0, ["netem", "delay", "25ms"]),
        (25, 5, 0, ["netem", "delay", "25ms", "5ms"]),
        (25, 5, 0.1, ["netem", "delay", "25ms", "5ms", "loss", "0.1%"]),
        (0, 0, 1, ["netem", "loss", "1%"]),
        (0, 5, 0, ["netem"]),
    ],
)
def test_the_arguments_of_netem(delay, jitter, loss, expected):
    assert lab.netem_arguments(delay, jitter, loss) == expected


def test_each_node_is_on_a_network_of_its_own_and_only_the_router_joins_them():
    text = lab.compose_file(Path("/data"), 1000, 1000)

    for index in range(lab.COUNT):
        assert f"net{index}:\n        ipv4_address: {lab.node_address(index)}" in text
        assert f"net{index}:\n        ipv4_address: {lab.router_address(index)}" in text
        assert f"subnet: 172.30.{index}.0/24" in text

    assert lab.node_address(0) != lab.node_address(1)
    assert 'net.ipv4.ip_forward: "1"' in text


def test_a_node_has_no_capabilities_and_only_the_router_does():
    text = lab.compose_file(Path("/data"), 1000, 1000)
    assert text.count('cap_drop: ["ALL"]') == lab.COUNT
    assert text.count("cap_add:") == 1
    assert text.index("cap_add") > text.index("router:")
    assert text.count('user: "1000:1000"') == lab.COUNT


def test_isolating_and_healing_are_opposite():
    assert lab.isolate_command("eth2").endswith("ip link set eth2 down")
    assert lab.heal_command("eth2").endswith("ip link set eth2 up")


# --- The measure, on real processes ----------------------------------------------------------------


@pytest.fixture
def running(tmp_path):
    made = Deployment(tmp_path)
    made.start_all()
    clients = [
        Client(made.api_url(index), token=(made.directory(index) / "api.token").read_text().strip())
        if (made.directory(index) / "api.token").exists()
        else Client(made.api_url(index))
        for index in range(made.count)
    ]
    with evidence.evidence_on_failure(made, clients, made.sender["account"], lambda: 0, "not-connected"):
        measure_module.wait_connected(clients)

    yield made, clients
    made.stop_all()


def test_a_measure_on_real_processes_says_what_happened(running):
    made, clients = running
    sender = measure_module.Sender(Identity.load(made.sender_key))

    def isolate():
        made.kill(3)

    def heal():
        made.start(3, create=False)

    account = sender.identity.identity_id

    with evidence.evidence_on_failure(
        made, clients, account, lambda: sender.next_nonce, "a-measure-on-real-processes"
    ):
        results = measure_module.measure_all(clients, sender, 3, 50, 20, isolate, heal)
        assert results["same_state_on_all"]
        assert results["latency"]["events"] == 3
        assert results["latency"]["median_ms"] > 0
        assert results["throughput"]["events_per_second"] > 0
        assert results["recovery"]["events_missed"] == 20
        assert all(client.account(account)["next_nonce"] == 73 for client in clients)


def test_isolation_that_cuts_off_nothing_is_an_error(running):
    # A number measured with no partition would look like a very good recovery.
    _, clients = running
    made = running[0]
    sender = measure_module.Sender(Identity.load(made.sender_key))
    with pytest.raises(measure_module.IsolationFailed):
        measure_module.measure_recovery(clients, sender, 5, lambda: None, lambda: None)


def test_healing_happens_also_when_the_measure_fails(running):
    made, clients = running
    sender = measure_module.Sender(Identity.load(made.sender_key))
    healed = []
    with pytest.raises(measure_module.IsolationFailed):
        measure_module.measure_recovery(clients, sender, 5, lambda: None, lambda: healed.append(1))
    assert healed == [1]


def test_a_node_that_does_not_answer_counts_as_not_there(tmp_path):
    client = Client("http://127.0.0.1:9")
    assert measure_module.next_nonce_of(client, "x") is None


def test_waiting_ends_with_an_error_and_not_for_ever():
    client = Client("http://127.0.0.1:9")
    with pytest.raises(measure_module.TimedOut):
        measure_module.wait_for([client], "x", 1, 0.05)


class Answering(Client):
    """A client that says one thing."""

    def __init__(self, nonce, root="same", executed=None, url="http://127.0.0.1:9"):
        super().__init__(url, timeout=0.05)
        self.nonce = nonce
        self.root = root
        self.executed = nonce if executed is None else executed

    def account(self, _account):
        return {"next_nonce": self.nonce}

    def status(self):
        return {"state_root": self.root, "executed": self.executed}


def test_waiting_is_for_every_node_and_not_only_the_first():
    with pytest.raises(measure_module.TimedOut, match="1 NODES"):
        measure_module.wait_for([Answering(5), Answering(0)], "x", 5, 0.05)


def test_a_measure_keeps_under_the_window_of_a_node():
    identity = Identity.create()
    sender = measure_module.Sender(identity)
    events = [sender.next() for _ in range(measure_module.MAX_ON_THEIR_WAY + measure_module.BATCH)]
    sent = []

    class Stuck(Answering):
        def submit_many(self, batch):
            sent.extend(batch)

    with pytest.raises(measure_module.TimedOut):
        import unittest.mock

        with unittest.mock.patch.object(
            measure_module,
            "wait_for",
            side_effect=measure_module.TimedOut("STOPPED"),
        ):
            measure_module.send_paced([Stuck(0)], identity.identity_id, events)

    assert 0 < len(sent) <= measure_module.MAX_ON_THEIR_WAY


def test_a_measure_waits_for_the_nodes_to_see_each_other():
    class Status:
        def __init__(self, peers):
            self.peers = peers

        def status(self):
            return {"peers": self.peers}

    measure_module.wait_connected([Status(["b"]), Status(["a"])], 0.05)
    with pytest.raises(measure_module.TimedOut):
        measure_module.wait_connected([Status(["b"]), Status([])], 0.05)


def test_a_percentile_is_one_of_the_values():
    values = [float(n) for n in range(100)]
    assert measure_module.percentile(values, 0.95) == 95.0
    assert measure_module.percentile([1.0], 0.95) == 1.0


def test_a_sender_counts_its_nonces():
    identity = Identity.create()
    sender = measure_module.Sender(identity, 5)
    assert sender.next().transfer == Transfer(identity.identity_id, "receiver", 1, 5)
    assert sender.next_nonce == 6


# --- What a failure says ---------------------------------------------------------------------------


def verdicts(diagnosis):
    return [node["verdict"] for node in diagnosis["nodes"]]


def test_no_answer_is_not_the_same_as_an_event_not_run():
    silent = Client("http://127.0.0.1:9", timeout=0.05)
    diagnosis = measure_module.diagnose([silent, Answering(1), Answering(5)], "x", 5)
    assert verdicts(diagnosis) == [
        measure_module.API_NOT_ANSWERING,
        measure_module.EVENT_NOT_RUN,
        measure_module.EVENT_RUN,
    ]


def test_an_error_from_the_api_is_an_answer():
    class Refusing(Answering):
        def account(self, _account):
            raise measure_module.ApiError(503, {"error": "no"})

    assert verdicts(measure_module.diagnose([Refusing(0)], "x", 1)) == [measure_module.API_ERROR]


def test_waiting_ends_with_what_each_node_said():
    silent = Client("http://127.0.0.1:9", timeout=0.05)

    with pytest.raises(measure_module.TimedOut, match="2 NODES NOT AT NONCE 5") as caught:
        measure_module.wait_for([silent, Answering(3), Answering(5)], "x", 5, 0.05)

    assert f"1 {measure_module.API_NOT_ANSWERING}" in str(caught.value)
    assert f"1 {measure_module.EVENT_NOT_RUN}" in str(caught.value)
    nodes = caught.value.diagnosis["nodes"]
    assert nodes[0]["while_waiting"]["unanswered"] == nodes[0]["while_waiting"]["polls"] > 0
    assert nodes[0]["while_waiting"]["last_nonce"] is None
    assert nodes[1]["while_waiting"]["unanswered"] == 0
    assert nodes[1]["while_waiting"]["last_nonce"] == 3


def test_a_watch_knows_when_a_node_last_moved():
    watch = measure_module.Watch()
    assert watch.see(3) == 3
    assert watch.see(None) is None
    moved = watch.last_progress
    watch.see(3)
    assert watch.last_progress == moved
    watch.see(4)
    assert watch.last_progress > moved
    assert watch.report()["unanswered"] == 1


def test_roots_that_differ_at_the_same_point_are_a_disagreement():
    diagnosis = measure_module.diagnose([Answering(5, "a"), Answering(5, "b"), Answering(5, "a")], "x", 5)
    assert diagnosis["states"]["disagreements"][0]["next_nonce"] == 5
    assert "STATE ROOTS DIFFER" in measure_module.summary_of(diagnosis)


def test_a_node_behind_is_no_disagreement_and_is_not_said_to_agree():
    behind = Answering(3, "old", url="http://127.0.0.1:8")
    diagnosis = measure_module.diagnose([Answering(5, "a"), Answering(5, "a"), behind], "x", 5)
    assert diagnosis["states"]["disagreements"] == []
    assert diagnosis["states"]["not_compared"] == [behind.base_url]
    assert "DIFFER" not in measure_module.summary_of(diagnosis)


def test_a_node_that_moved_during_the_reading_is_not_compared():
    class Moving(Answering):
        def account(self, _account):
            self.nonce += 1
            return {"next_nonce": self.nonce}

    moving = Moving(4, "other", executed=6, url="http://127.0.0.1:8")
    diagnosis = measure_module.diagnose([Answering(6, "a"), Answering(6, "a"), moving], "x", 6)
    assert diagnosis["nodes"][2]["moving"]
    assert diagnosis["states"]["disagreements"] == []
    assert moving.base_url in diagnosis["states"]["not_compared"]


def test_a_failure_is_kept_even_with_a_log_that_cannot_be_had(tmp_path):
    log = tmp_path / "n0" / "node.log"
    log.parent.mkdir()
    log.write_text("what it said\n")
    missing = tmp_path / "n1" / "node.log"
    out = tmp_path / "failure"
    collect = 'echo fetched > "$PSYSTEM_FAILURE_DIR/fetched.log"; exit 7'
    measure_module.save_failure(out, ValueError("x"), {"nodes": []}, [log, missing], collect)
    assert (out / "n0-node.log").read_text() == "what it said\n"
    assert (out / "fetched.log").read_text() == "fetched\n"
    report = json.loads((out / "diagnosis.json").read_text())
    assert "ValueError" in report["error"]
    assert [entry["log"] for entry in report["logs_missing"]] == [str(missing), collect]


def test_the_script_says_what_failed_and_keeps_it(tmp_path, monkeypatch, capsys):
    key = tmp_path / "sender.key"
    Identity.create().save(key)
    token = tmp_path / "token"
    token.write_text("t\n")
    out = tmp_path / "failure"
    monkeypatch.setattr(sys, "argv", [
        "measure_network.py",
        "--sender-key", str(key),
        "--api", f"http://127.0.0.1:9={token}",
        "--failure-dir", str(out),
        "--collect-logs", 'touch "$PSYSTEM_FAILURE_DIR/collected"',
    ])
    assert measure_module.main() == measure_module.MEASURE_FAILED
    printed = capsys.readouterr()
    assert printed.out == ""
    said = json.loads(printed.err.splitlines()[-1])
    assert verdicts(said["at_the_end"]) == [measure_module.API_NOT_ANSWERING]
    assert json.loads((out / "diagnosis.json").read_text())["error"] == said["error"]
    assert (out / "collected").exists()


def test_the_lab_asks_each_node_for_its_threads_before_its_log():
    text = lab.collect_logs_command()

    for index in range(lab.COUNT):
        assert f"{lab.PROJECT}-node-{index}-1" in text

    assert text.index("docker kill -s USR1") < text.index("docker logs")
    assert "$PSYSTEM_FAILURE_DIR" in text


@pytest.fixture
def stuck(tmp_path, monkeypatch):
    """A real event that cannot run: two of four nodes dead, so no quorum, and the two left only wait."""
    monkeypatch.setenv("PSYSTEM_FAILURE_DIR", str(tmp_path / "kept"))
    made = Deployment(tmp_path)
    made.start_all()
    clients = [Client(made.api_url(index), timeout=1.0) for index in range(made.count)]
    measure_module.wait_connected(clients)
    sender = measure_module.Sender(Identity.load(made.sender_key))
    clients[0].submit(sender.next())
    measure_module.wait_for(clients, sender.identity.identity_id, 1, 30.0)
    made.kill(2)
    made.kill(3)
    clients[0].submit(sender.next())
    yield made, clients, sender, tmp_path / "kept"
    made.stop_all()


def test_on_real_processes_a_dead_node_and_an_event_stuck_are_told_apart(stuck):
    made, clients, sender, _ = stuck
    account = sender.identity.identity_id

    with pytest.raises(measure_module.TimedOut) as caught:
        measure_module.wait_for(clients, account, sender.next_nonce, 0.5)

    assert verdicts(caught.value.diagnosis) == [
        measure_module.EVENT_NOT_RUN,
        measure_module.EVENT_NOT_RUN,
        measure_module.API_NOT_ANSWERING,
        measure_module.API_NOT_ANSWERING,
    ]
    assert caught.value.diagnosis["states"]["disagreements"] == []
    assert caught.value.diagnosis["nodes"][0]["metrics"]["psystem_peers_connected"] == 1


def test_on_real_processes_an_api_that_hangs_is_not_an_event_not_run(running):
    # The process is alive and the port is open, and it does not answer: not what a dead node looks like.
    made, clients = running
    made.processes[1].send_signal(signal.SIGSTOP)

    try:
        slow = [Client(made.api_url(index), timeout=0.5) for index in range(made.count)]
        diagnosis = measure_module.diagnose(slow, made.sender["account"], 1)
    finally:
        made.processes[1].send_signal(signal.SIGCONT)

    assert verdicts(diagnosis)[1] == measure_module.API_NOT_ANSWERING
    assert verdicts(diagnosis)[0] == measure_module.EVENT_NOT_RUN
    assert evidence.process_states(made)["node-1"] == "running"


def test_a_test_that_fails_leaves_what_its_nodes_said(stuck, capsys):
    made, clients, sender, kept = stuck
    account = sender.identity.identity_id

    with pytest.raises(measure_module.TimedOut) as caught:
        with evidence.evidence_on_failure(made, clients, account, lambda: sender.next_nonce, "stuck"):
            measure_module.wait_for(clients, account, sender.next_nonce, 0.5)

    directory = next(kept.iterdir())
    report = json.loads((directory / "diagnosis.json").read_text())
    assert report["error"] == repr(caught.value)
    assert report["when_it_gave_up"]["nonce"] == 2
    assert report["processes"]["node-0"] == "running"
    assert report["processes"]["node-2"] == "not running: stopped by the test"
    # A store of a node that died by SIGKILL still has what it wrote.
    assert (directory / "node-2-votes.sqlite").exists()

    # Where the event stopped: on the two nodes that can vote, with no certificate on either.
    row = next(row for row in report["stores"]["not_certified_everywhere"] if row["nonce"] == 1)
    assert row["certified_by"] == []
    assert {"node-0", "node-1"} <= set(row["voted_by"])
    assert report["stores"]["different_events_for_a_nonce"] == []

    # Both dumps of the threads got into the log that was kept, and into what pytest prints.
    assert (directory / "n0-node.log").read_text().count("most recent call first") >= 2
    printed = capsys.readouterr().out
    assert str(directory) in printed
    assert "LOG OF n0" in printed


def test_a_test_that_passes_leaves_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("PSYSTEM_FAILURE_DIR", str(tmp_path / "kept"))

    with evidence.evidence_on_failure(None, [], "x", lambda: 0, "fine"):
        pass

    assert not (tmp_path / "kept").exists()


def test_a_failure_goes_on_also_when_the_evidence_cannot_be_saved(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("PSYSTEM_FAILURE_DIR", str(tmp_path))

    with pytest.raises(ZeroDivisionError):
        with evidence.evidence_on_failure(None, [], "x", lambda: 0, "broken"):
            1 / 0

    assert "EVIDENCE WAS NOT SAVED" in capsys.readouterr().out


def test_stores_show_two_events_for_one_nonce():
    compared = evidence.compare_stores(
        {
            "a": {"voted": {0: "one", 1: "two"}, "certified": {0: "one"}},
            "b": {"voted": {0: "one", 1: "other"}, "certified": {0: "one"}},
        },
        3,
    )
    assert compared["voted_by_none"] == [2]
    assert compared["different_events_for_a_nonce"] == [1]
    assert compared["not_certified_everywhere"] == [
        {"nonce": 1, "voted_by": ["a", "b"], "certified_by": []}
    ]
    assert compared["highest_nonce_seen"] == 1


def test_a_copy_of_a_store_is_of_the_committed_data(tmp_path):
    source = tmp_path / "source.sqlite"

    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE t (x)")
        connection.execute("INSERT INTO t VALUES (1)")

    target = tmp_path / "copy.sqlite"
    evidence.copy_store(source, target)

    with sqlite3.connect(target) as connection:
        assert connection.execute("SELECT x FROM t").fetchall() == [(1,)]


def test_the_wait_of_a_measure_can_be_set_for_a_search():
    done = subprocess.run(
        [sys.executable, "-c", "from scripts.measure_network import LONG_WAIT_SECONDS as w; print(w)"],
        cwd=evidence.ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "PSYSTEM_MEASURE_WAIT_SECONDS": "7"},
    )
    assert done.stdout.strip() == "7.0", done.stderr
