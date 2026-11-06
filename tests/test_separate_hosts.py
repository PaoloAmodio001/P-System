"""The files for nodes on separate machines, and the measure, on four real processes.

Docker and four machines cannot run here in the suite: they ran by hand, and docs/BENCHMARKS.md says
when and what. What can run here is that the files are what a node reads, that the commands of the lab
are what they should be, and that a measure says what really happened, on real processes.
"""

from pathlib import Path

import pytest

from core.event import Transfer
from crypto.identity import Identity
from network.deployment import read_genesis, read_node_config
from scripts import make_host_deployment as hosts_module
from scripts import measure_network as measure_module
from scripts import netem_lab as lab
from sdk.client import Client
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

    results = measure_module.measure_all(clients, sender, 3, 50, 20, isolate, heal)
    assert results["same_state_on_all"]
    assert results["latency"]["events"] == 3
    assert results["latency"]["median_ms"] > 0
    assert results["throughput"]["events_per_second"] > 0
    assert results["recovery"]["events_missed"] == 20
    account = sender.identity.identity_id
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


class Answering:
    """A client that says one thing."""

    def __init__(self, nonce):
        self.nonce = nonce

    def account(self, _account):
        return {"next_nonce": self.nonce}


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
