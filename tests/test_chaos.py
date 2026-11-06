"""Faults on the network between real processes: see tests/chaos.py."""

import random
import socket
import threading

import pytest

from tests.chaos import Campaign, ChaosDeployment, Link, Proxy, Report


@pytest.mark.slow
@pytest.mark.parametrize("seed", [20261105, 20261106])
def test_a_campaign_of_faults_breaks_nothing(tmp_path, seed):
    deployment = ChaosDeployment(tmp_path, random.Random(seed), extra_senders=1, balance=100_000)
    deployment.start_all()
    try:
        report = Campaign(deployment, seed).run(seconds=40)
    finally:
        deployment.close()
    print(report.to_json())
    assert report.safe, report.to_json()
    assert report.honest_final == report.submitted > 0
    assert report.faults


@pytest.mark.slow
@pytest.mark.parametrize("seed", [20261107, 20261108])
def test_a_committee_change_in_a_campaign_of_faults(tmp_path, seed):
    deployment = ChaosDeployment(tmp_path, random.Random(seed), extra_senders=1, balance=100_000)
    deployment.start_all()
    try:
        report = Campaign(deployment, seed, epoch_change=Campaign.change_committee).run(seconds=40)
    finally:
        deployment.close()
    print(report.to_json())
    assert report.safe, report.to_json()
    assert report.honest_final == report.submitted > 0
    assert report.epoch == 1


# The checks and the proxy must be able to fail: a campaign that cannot see a fork proves nothing.


class FakeClient:
    def __init__(self, certificates=None, balances=None):
        self.certificates = certificates or {}
        self.balances = balances or {}

    def certificate(self, event_id):
        return self.certificates.get(event_id)

    def closures(self):
        return []

    def account(self, account):
        return {"balance": self.balances.get(account, 0)}


def bare_campaign(tmp_path, clients):
    from core.attestation import Committee, Governance
    from core.state import State
    from crypto.identity import Identity
    from network.deployment import write_genesis

    campaign = Campaign.__new__(Campaign)
    members = sorted((Identity.create() for _ in range(4)), key=lambda m: m.public_key)
    signers = [Identity.create() for _ in range(3)]
    write_genesis(
        tmp_path / "genesis.json",
        [m.public_key for m in members],
        1,
        {"x": 1},
        [signer.public_key for signer in signers],
        2,
    )
    campaign.deployment = type("D", (), {"base": tmp_path, "count": len(clients), "balance_per_sender": 10})()
    campaign.report = Report(1)
    campaign.clients = clients
    campaign.down = set()
    campaign.known = {}
    campaign.honest_identity = Identity.create()
    campaign.equivocator = Identity.create()
    campaign.members = members
    return campaign


def certificate_for(event, members, tmp_path):
    from core.attestation import QuorumCertificate, Vote
    from network.deployment import read_genesis
    from network.message import encode_certificate

    committee = read_genesis(tmp_path / "genesis.json").committee
    votes = tuple(Vote.create(committee, member, event) for member in members[:3])
    return encode_certificate(QuorumCertificate(event, votes))


def test_two_certified_alternatives_are_seen(tmp_path):
    from core.event import Transfer

    first = Transfer("a", "bob", 1, 0)
    second = Transfer("a", "carol", 1, 0)
    campaign = bare_campaign(tmp_path, [FakeClient(), FakeClient()])
    campaign.known[("a", 0)] = [first, second]
    campaign.clients[0].certificates[first.event_id()] = certificate_for(first, campaign.members, tmp_path)
    campaign.clients[1].certificates[second.event_id()] = certificate_for(second, campaign.members, tmp_path)
    campaign._check_safety()
    assert any("two certified" in problem for problem in campaign.report.problems)
    assert campaign.report.certified_alternatives == 2


def test_one_certified_alternative_is_no_problem(tmp_path):
    from core.event import Transfer

    first = Transfer("a", "bob", 1, 0)
    campaign = bare_campaign(tmp_path, [FakeClient(), FakeClient()])
    campaign.known[("a", 0)] = [first]
    for client in campaign.clients:
        client.certificates[first.event_id()] = certificate_for(first, campaign.members, tmp_path)
    campaign._check_safety()
    assert campaign.report.safe


def test_a_certificate_that_does_not_verify_is_seen(tmp_path):
    from core.event import Transfer

    first = Transfer("a", "bob", 1, 0)
    campaign = bare_campaign(tmp_path, [FakeClient()])
    campaign.known[("a", 0)] = [first]
    body = certificate_for(first, campaign.members, tmp_path)
    body["votes"] = body["votes"][:1]
    campaign.clients[0].certificates[first.event_id()] = body
    campaign._check_safety()
    assert any("does not verify" in problem for problem in campaign.report.problems)


def test_balances_that_do_not_add_up_are_seen(tmp_path):
    campaign = bare_campaign(tmp_path, [FakeClient(balances={"bob": 21})])
    campaign._check_balances()
    assert any("add up" in problem for problem in campaign.report.problems)


def test_balances_that_add_up_are_no_problem(tmp_path):
    campaign = bare_campaign(tmp_path, [FakeClient(balances={"bob": 20})])
    campaign._check_balances()
    assert campaign.report.safe


@pytest.fixture
def echo():
    server = socket.create_server(("127.0.0.1", 0))

    def run():
        while True:
            try:
                connection, _ = server.accept()
            except OSError:
                return

            def serve(accepted=connection):
                with accepted:
                    while data := accepted.recv(65536):
                        accepted.sendall(data)

            threading.Thread(target=serve, daemon=True).start()

    threading.Thread(target=run, daemon=True).start()
    yield server.getsockname()[1]
    server.close()


def through(port, link, data=b"hello"):
    proxy = Proxy(port, link)
    try:
        with socket.create_connection(("127.0.0.1", proxy.port), timeout=2) as client:
            client.settimeout(1.5)
            client.sendall(data)
            try:
                return client.recv(100)
            except OSError:
                return None
    finally:
        proxy.close()


def test_a_clear_link_passes_bytes(echo):
    assert through(echo, Link(random.Random(1))) == b"hello"


def test_a_blocked_link_passes_nothing(echo):
    link = Link(random.Random(1))
    link.blocked = True
    assert through(echo, link) in (None, b"")


def test_a_stalled_link_passes_nothing(echo):
    link = Link(random.Random(1))
    link.stalled = True
    assert through(echo, link) is None


def test_a_link_that_corrupts_changes_bytes(echo):
    link = Link(random.Random(1))
    link.corrupt_chance = 1.0
    answer = through(echo, link)
    assert answer is not None and answer != b"hello" and len(answer) == 5


def test_a_link_that_cuts_closes_the_connection(echo):
    link = Link(random.Random(1))
    link.cut_chance = 1.0
    assert through(echo, link) in (None, b"")


def test_a_socket_closed_by_the_other_direction_ends_the_forward_quietly():
    # The other direction closes both sockets when it ends, and it can do so before this one starts.
    link = Link(random.Random(1))
    proxy = Proxy(1, link)
    source, target = socket.socketpair()
    source.close()

    try:
        proxy._forward(source, target, link.generation)
    finally:
        proxy.close()

    assert target.fileno() == -1
