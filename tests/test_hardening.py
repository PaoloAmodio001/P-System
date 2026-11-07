"""Keys at rest, a signer in another process, TLS and limits on the API, pacing, revocation."""

import json
import os
import socket
import ssl
import stat
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import replace
from pathlib import Path

import pytest

from core.attestation import Committee, Vote, vote_payload
from core.event import Transfer
from core.signed_event import SignedTransfer
from core.state import State
from crypto.identity import Identity, verify_signature
from network.deployment import DeploymentError, read_node_config, read_passphrase, write_genesis
from network.node import Node
from network.node_tls_identity import create_authority, issue_node_certificate
from network.peer import Peer
from network.peer_connection import Pacer
from network.quorum import QuorumConfig, QuorumReplica, SqliteVoteStore
from network.remote_signer import (
    EPOCH_REPORT_DOMAIN,
    VOTE_DOMAIN,
    RemoteIdentity,
    SignerGuard,
    SignerServer,
    SignerUnavailable,
)
from network.secure_transport import SecureTransport
from network.service import MAX_TRACKED_CLIENTS, RateLimiter, Service
from sdk.client import ApiError, Client
from tests.die_with_parent import command
from tests.deployment_helpers import ROOT, Deployment, psystem, wait_until

A = Transfer("alice", "bob", 8, 0)
B = Transfer("alice", "carol", 8, 0)
C = Transfer("alice", "bob", 8, 1)
COMMITTEE_ID = b"\x11" * 32
OTHER_COMMITTEE = b"\x22" * 32


def vote_bytes(event, committee=COMMITTEE_ID):
    return VOTE_DOMAIN + committee + event.canonical()


def report_bytes(digest=b"\x33" * 32, change=b"\x44" * 32, committee=COMMITTEE_ID):
    return EPOCH_REPORT_DOMAIN + committee + change + digest


# Keys at rest.


def test_an_encrypted_key_comes_back(tmp_path):
    identity = Identity.create()
    identity.save(tmp_path / "k", b"secret words")
    assert Identity.load(tmp_path / "k", b"secret words").public_key == identity.public_key


def test_an_encrypted_key_file_is_encrypted(tmp_path):
    Identity.create().save(tmp_path / "k", b"secret words")
    assert b"ENCRYPTED PRIVATE KEY" in (tmp_path / "k").read_bytes()


def test_a_plain_key_file_is_marked_plain(tmp_path):
    Identity.create().save(tmp_path / "k")
    assert b"ENCRYPTED" not in (tmp_path / "k").read_bytes()


@pytest.mark.parametrize("given", [b"wrong", None])
def test_an_encrypted_key_needs_its_passphrase(tmp_path, given):
    Identity.create().save(tmp_path / "k", b"secret words")
    with pytest.raises(ValueError):
        Identity.load(tmp_path / "k", given)


def test_a_passphrase_on_a_plain_key_is_an_error(tmp_path):
    Identity.create().save(tmp_path / "k")
    with pytest.raises(ValueError):
        Identity.load(tmp_path / "k", b"not needed")


def test_a_passphrase_file_others_can_read_is_refused(tmp_path):
    path = tmp_path / "p"
    path.write_text("x")
    path.chmod(0o640)
    with pytest.raises(DeploymentError):
        read_passphrase(path)


def test_an_empty_passphrase_file_is_refused(tmp_path):
    path = tmp_path / "p"
    path.write_text("\n")
    path.chmod(0o600)
    with pytest.raises(DeploymentError):
        read_passphrase(path)


def test_the_command_writes_and_reads_an_encrypted_key(tmp_path):
    passphrase = tmp_path / "p"
    passphrase.write_text("words\n")
    passphrase.chmod(0o600)
    key = tmp_path / "k"
    made = json.loads(psystem("key", "generate", str(key), "--passphrase-file", str(passphrase)))
    shown = json.loads(psystem("key", "show", str(key), "--passphrase-file", str(passphrase)))
    assert made == shown
    assert b"ENCRYPTED" in key.read_bytes()


# The guard of the signer.


@pytest.fixture
def guard(tmp_path):
    made = SignerGuard(tmp_path / "guard.sqlite")
    yield made
    made.close()


def test_a_first_vote_is_allowed_and_again(guard):
    assert guard.permit(vote_bytes(A))
    assert guard.permit(vote_bytes(A))


def test_another_event_for_one_spend_is_refused(guard):
    assert guard.permit(vote_bytes(A))
    assert not guard.permit(vote_bytes(B))


def test_another_nonce_is_another_spend(guard):
    assert guard.permit(vote_bytes(A))
    assert guard.permit(vote_bytes(C))


def test_another_sender_is_another_spend(guard):
    assert guard.permit(vote_bytes(A))
    assert guard.permit(vote_bytes(Transfer("dave", "carol", 8, 0)))


def test_another_committee_is_another_lock(guard):
    assert guard.permit(vote_bytes(A))
    assert guard.permit(vote_bytes(B, OTHER_COMMITTEE))


def test_the_lock_survives_a_restart(tmp_path):
    first = SignerGuard(tmp_path / "g")
    assert first.permit(vote_bytes(A))
    first.close()
    second = SignerGuard(tmp_path / "g")
    assert not second.permit(vote_bytes(B))
    second.close()


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"anything at all",
        b"P-SYSTEM/EPOCH-CHANGE/v1\0" + b"x" * 80,
        VOTE_DOMAIN,
        VOTE_DOMAIN + b"\x11" * 32,
        VOTE_DOMAIN + b"\x11" * 32 + b"not json",
        VOTE_DOMAIN + b"\x11" * 32 + b"[1, 2]",
        VOTE_DOMAIN + b"\x11" * 32 + b'{"sender": "a"}',
        VOTE_DOMAIN + b"\x11" * 32 + b'{"nonce": 1}',
        VOTE_DOMAIN + b"\x11" * 32 + b'{"sender": 7, "nonce": 1}',
        VOTE_DOMAIN + b"\x11" * 32 + b'{"sender": "a", "nonce": "1"}',
        VOTE_DOMAIN + b"\x11" * 8,
        EPOCH_REPORT_DOMAIN,
        EPOCH_REPORT_DOMAIN + b"\x11" * 95,
        EPOCH_REPORT_DOMAIN + b"\x11" * 97,
    ],
)
def test_what_it_does_not_recognize_is_refused(guard, payload):
    assert not guard.permit(payload)


def test_a_report_is_one_per_order(guard):
    assert guard.permit(report_bytes())
    assert guard.permit(report_bytes())
    assert not guard.permit(report_bytes(digest=b"\x55" * 32))


def test_one_order_for_each_committee(guard):
    assert guard.permit(report_bytes())
    # Another order of one committee: two orders with a quorum could mean two next committees.
    assert not guard.permit(report_bytes(digest=b"\x55" * 32, change=b"\x66" * 32))
    assert guard.permit(report_bytes(digest=b"\x55" * 32, committee=OTHER_COMMITTEE))


# The signer.


@pytest.fixture
def signer(tmp_path):
    identity = Identity.create()
    server = SignerServer(identity, tmp_path / "s.sock", tmp_path / "guard.sqlite")
    server.start()
    yield server, identity
    server.stop()


def test_a_signature_of_the_signer_verifies(signer):
    server, identity = signer
    remote = RemoteIdentity(server.socket_path)
    assert remote.public_key == identity.public_key
    assert remote.identity_id == identity.identity_id
    payload = vote_bytes(A)
    assert verify_signature(identity.public_key, remote.sign(payload), payload)


def test_a_double_vote_gets_no_signature(signer):
    server, _ = signer
    remote = RemoteIdentity(server.socket_path)
    remote.sign(vote_bytes(A))
    with pytest.raises(SignerUnavailable, match="REFUSED"):
        remote.sign(vote_bytes(B))
    # The connection is still good.
    assert remote.sign(vote_bytes(A))


def test_only_its_owner_can_reach_the_socket(signer):
    server, _ = signer
    assert stat.S_IMODE(server.socket_path.stat().st_mode) == 0o600


def test_a_file_at_the_path_of_the_socket_is_left_alone(tmp_path):
    path = tmp_path / "s.sock"
    path.write_text("mine")
    server = SignerServer(Identity.create(), path, tmp_path / "g")
    with pytest.raises(ValueError):
        server.start()
    assert path.read_text() == "mine"


def test_a_socket_left_behind_is_replaced(tmp_path):
    path = tmp_path / "s.sock"
    left = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    left.bind(str(path))
    left.close()
    server = SignerServer(Identity.create(), path, tmp_path / "g")
    server.start()
    assert RemoteIdentity(path).public_key == server.public_key
    server.stop()


def test_no_signer_at_the_start_is_an_error(tmp_path):
    with pytest.raises(SignerUnavailable):
        RemoteIdentity(tmp_path / "none.sock")


def test_a_signer_that_goes_and_comes_back(tmp_path):
    identity = Identity.create()
    path = tmp_path / "s.sock"
    server = SignerServer(identity, path, tmp_path / "g")
    server.start()
    remote = RemoteIdentity(path)
    remote.sign(vote_bytes(A))
    server.stop()
    with pytest.raises(SignerUnavailable):
        remote.sign(vote_bytes(A))
    server = SignerServer(identity, path, tmp_path / "g")
    server.start()
    assert remote.sign(vote_bytes(A))
    with pytest.raises(SignerUnavailable, match="REFUSED"):
        remote.sign(vote_bytes(B))
    server.stop()


def test_an_oversized_request_ends_the_connection(signer):
    server, _ = signer
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as raw:
        raw.settimeout(2)
        raw.connect(str(server.socket_path))
        raw.sendall(b"S" + (2**31).to_bytes(4, "big"))
        assert raw.recv(1) == b""


def test_an_unknown_request_ends_the_connection(signer):
    server, _ = signer
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as raw:
        raw.settimeout(2)
        raw.connect(str(server.socket_path))
        raw.sendall(b"?")
        assert raw.recv(1) == b""


def replica_with(tmp_path, identity, committee, genesis):
    store = SqliteVoteStore(tmp_path / "v.sqlite", committee, identity.public_key, create=True)
    return QuorumReplica(identity, genesis, store, lambda event: True), store


def test_a_replica_with_a_signer_votes_and_stays_honest_when_refused(signer, tmp_path):
    server, identity = signer
    sender = Identity.create()
    genesis = State({sender.identity_id: 10})
    others = [Identity.create().public_key for _ in range(3)]
    committee = Committee.create([identity.public_key, *others], 1, genesis)
    replica, store = replica_with(tmp_path, RemoteIdentity(server.socket_path), committee, genesis)
    event = Transfer(sender.identity_id, "bob", 1, 0)
    vote = replica.handle_vote_request(event)
    assert vote.verify(committee, event)

    # A file restored from an old backup, which forgot the vote: the node would vote again for
    # something else. The signer says no.
    store._connection.execute("DELETE FROM votes")
    other = Transfer(sender.identity_id, "carol", 1, 0)
    assert replica.handle_vote_request(other) is None
    store.close()


def test_a_vote_when_the_signer_is_away_is_no_vote_and_can_be_asked_again(tmp_path):
    identity = Identity.create()
    path = tmp_path / "s.sock"
    server = SignerServer(identity, path, tmp_path / "g")
    server.start()
    remote = RemoteIdentity(path)
    sender = Identity.create()
    genesis = State({sender.identity_id: 10})
    others = [Identity.create().public_key for _ in range(3)]
    committee = Committee.create([identity.public_key, *others], 1, genesis)
    replica, store = replica_with(tmp_path, remote, committee, genesis)
    event = Transfer(sender.identity_id, "bob", 1, 0)
    server.stop()
    assert replica.handle_vote_request(event) is None
    server = SignerServer(identity, path, tmp_path / "g")
    server.start()
    assert replica.handle_vote_request(event) is not None
    server.stop()
    store.close()


def test_the_payload_format_is_what_the_guard_understands():
    # If attestation changes what it signs, the guard must be changed on purpose.
    sender = Identity.create()
    genesis = State({sender.identity_id: 10})
    committee = Committee.create([Identity.create().public_key for _ in range(4)], 1, genesis)
    assert vote_payload(committee, A) == VOTE_DOMAIN + bytes.fromhex(committee.committee_id) + A.canonical()


@pytest.mark.slow
def test_four_real_nodes_with_signers_certify_and_change_epoch(tmp_path):
    deployment = Deployment(tmp_path)
    signers = []

    try:
        for index in range(4):
            directory = deployment.directory(index)
            sock = directory / "s.sock"
            process = subprocess.Popen(
                command(
                    "-m", "network.cli", "signer",
                    "--key", str(directory / "identity.key"),
                    "--socket", str(sock),
                    "--guard", str(directory / "guard.sqlite"),
                ),
                cwd=ROOT,
                stdout=subprocess.PIPE,
                text=True,
            )
            signers.append(process)
            assert json.loads(process.stdout.readline())["socket"] == str(sock)
            config = directory / "node.toml"
            config.write_text(
                config.read_text().replace('identity_key = "identity.key"', 'identity_signer = "s.sock"')
            )

        deployment.start_all()
        api = [Client(deployment.api_url(i)) for i in range(4)]
        assert wait_until(lambda: all(len(c.status()["peers"]) == 3 for c in api))

        key = Identity.load(deployment.sender_key)
        spend = SignedTransfer.create(key, Transfer(key.identity_id, "bob", 1, 0))
        assert api[0].submit(spend)["accepted"]
        assert wait_until(lambda: all(c.status()["executed"] == 1 for c in api))

        from core.attestation import EpochChange
        from network.deployment import read_genesis
        from network.message import encode_epoch_change

        genesis = read_genesis(tmp_path / "genesis.json")
        change = EpochChange.create(
            genesis.committee,
            [bytes.fromhex(m["public_key"]) for m in deployment.members],
            1,
            genesis.governance,
            [Identity.load(p) for p in deployment.governance_keys[:2]],
        )
        api[0]._request("POST", "/v1/epoch-changes", encode_epoch_change(change)["change"])
        assert wait_until(lambda: all(c.status()["epoch"] == 1 for c in api))

        second = SignedTransfer.create(key, Transfer(key.identity_id, "bob", 1, 1))
        assert api[1].submit(second)["accepted"]
        assert wait_until(lambda: all(c.status()["executed"] == 2 for c in api))
    finally:
        deployment.stop_all()
        for process in signers:
            process.terminate()
            process.wait(timeout=10)


# Limits.


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def test_a_limiter_allows_the_burst_and_no_more():
    limiter = RateLimiter(10, 3, Clock())
    assert [limiter.allow("a") for _ in range(4)] == [True, True, True, False]
    assert limiter.rejected == 1


def test_a_limiter_fills_up_with_time():
    clock = Clock()
    limiter = RateLimiter(10, 3, clock)
    for _ in range(3):
        limiter.allow("a")
    assert not limiter.allow("a")
    clock.now += 0.11
    assert limiter.allow("a")
    assert not limiter.allow("a")


def test_a_limiter_does_not_fill_beyond_the_burst():
    clock = Clock()
    limiter = RateLimiter(10, 3, clock)
    limiter.allow("a")
    clock.now += 1000
    assert [limiter.allow("a") for _ in range(4)] == [True, True, True, False]


def test_each_client_has_its_own_bucket():
    limiter = RateLimiter(10, 1, Clock())
    assert limiter.allow("a")
    assert not limiter.allow("a")
    assert limiter.allow("b")


def test_a_charge_can_go_below_zero():
    clock = Clock()
    limiter = RateLimiter(10, 3, clock)
    limiter.charge("a", 13)
    assert not limiter.allow("a")
    clock.now += 1.0
    assert not limiter.allow("a")
    clock.now += 0.11
    assert limiter.allow("a")


def test_a_limiter_stays_in_bounded_memory():
    limiter = RateLimiter(10, 1, Clock())
    for number in range(MAX_TRACKED_CLIENTS + 5):
        limiter.allow(str(number))
    assert len(limiter._clients) == MAX_TRACKED_CLIENTS
    assert "0" not in limiter._clients
    assert str(MAX_TRACKED_CLIENTS + 4) in limiter._clients


def test_concurrent_tokens_do_not_double_consume():
    import threading

    limiter = RateLimiter(rate=0, burst=10, clock=Clock())
    results = []
    lock = threading.Lock()
    barrier = threading.Barrier(20)

    def worker():
        barrier.wait()
        allowed = limiter.allow("client")
        with lock:
            results.append(allowed)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sum(1 for r in results if r) == 10
    assert sum(1 for r in results if not r) == 10
    assert limiter.rejected == 10


def test_a_pacer_lets_a_burst_through_and_then_waits():
    clock = Clock()
    waits = []
    pacer = Pacer(100, 10, clock, waits.append)
    pacer.take(10)
    assert waits == []
    pacer.take(5)
    assert waits == [pytest.approx(0.05)]


def test_a_pacer_fills_up_with_time_up_to_its_burst():
    clock = Clock()
    waits = []
    pacer = Pacer(100, 10, clock, waits.append)
    pacer.take(10)
    clock.now += 1000
    pacer.take(10)
    assert waits == []
    pacer.take(1)
    assert waits == [pytest.approx(0.01)]


# The service.


@pytest.fixture
def layout(tmp_path):
    authority = create_authority(tmp_path / "ca")
    issue_node_certificate(authority, "api-node", tmp_path)
    issue_node_certificate(authority, "api-tls", tmp_path)
    sender = Identity.create()
    members = []
    for index in range(4):
        identity = Identity.create()
        identity.save(tmp_path / f"m{index}.key")
        members.append(identity)
    write_genesis(
        tmp_path / "genesis.json",
        [m.public_key for m in members],
        1,
        {sender.identity_id: 100},
    )
    return tmp_path


def write_config(base: Path, *lines: str, api: tuple[str, ...] = ()) -> Path:
    path = base / "node.toml"
    path.write_text(
        "\n".join(
            [
                'node_id = "api-node"',
                'host = "127.0.0.1"',
                "port = 0",
                'identity_key = "m0.key"',
                'tls_certificate = "api-node.crt"',
                'tls_key = "api-node.key"',
                'tls_authority = "ca/ca.crt"',
                'genesis = "genesis.json"',
                'store = "v.sqlite"',
                *lines,
                "[api]",
                "port = 0",
                *api,
            ]
        )
        + "\n"
    )
    return path


def service_with(base, *lines, api=()):
    return Service(read_node_config(write_config(base, *lines, api=api)), create=True)


def url(service, scheme="http", path="/v1/status"):
    return f"{scheme}://127.0.0.1:{service.api_address[1]}{path}"


def test_the_api_over_tls(layout):
    service = service_with(layout, api=('tls_certificate = "api-tls.crt"', 'tls_key = "api-tls.key"'))
    service.start()
    try:
        context = ssl.create_default_context(cafile=str(layout / "ca" / "ca.crt"))
        context.check_hostname = False
        with urllib.request.urlopen(url(service, "https"), context=context, timeout=5) as answer:
            assert json.loads(answer.read())["node_id"] == "api-node"
        with pytest.raises((urllib.error.URLError, ConnectionError, OSError)):
            urllib.request.urlopen(url(service), timeout=2)
    finally:
        service.stop()


def test_a_silent_client_on_tls_stops_nobody(layout):
    service = service_with(layout, api=('tls_certificate = "api-tls.crt"', 'tls_key = "api-tls.key"'))
    service.start()
    try:
        with socket.create_connection(("127.0.0.1", service.api_address[1])):
            context = ssl.create_default_context(cafile=str(layout / "ca" / "ca.crt"))
            context.check_hostname = False
            with urllib.request.urlopen(url(service, "https"), context=context, timeout=3) as answer:
                assert answer.status == 200
    finally:
        service.stop()


def test_a_certificate_of_the_authority_passes_strict_verification(layout):
    # The default context of Python, with VERIFY_X509_STRICT, is what most clients use.
    service = service_with(layout, api=('tls_certificate = "api-tls.crt"', 'tls_key = "api-tls.key"'))
    service.start()
    try:
        context = ssl.create_default_context(cafile=str(layout / "ca" / "ca.crt"))
        context.check_hostname = False
        assert context.verify_flags & ssl.VERIFY_X509_STRICT
        with socket.create_connection(("127.0.0.1", service.api_address[1]), timeout=5) as raw:
            with context.wrap_socket(raw) as secured:
                assert secured.version() in ("TLSv1.2", "TLSv1.3")
    finally:
        service.stop()


def test_the_client_of_the_sdk_checks_the_authority(layout):
    service = service_with(layout, api=('tls_certificate = "api-tls.crt"', 'tls_key = "api-tls.key"'))
    service.start()
    try:
        client = Client(url(service, "https", "").replace("127.0.0.1", "localhost"), ca_file=str(layout / "ca" / "ca.crt"))
        # The certificate names api-tls and not localhost: refusing is what it must do.
        with pytest.raises(OSError):
            client.status()
    finally:
        service.stop()


@pytest.mark.parametrize(
    "api",
    [
        ('tls_certificate = "a"',),
        ('tls_key = "a"',),
        ("requests_per_second = 0",),
        ("requests_per_second = -1",),
        ("burst = 0",),
        ('requests_per_second = "many"',),
        ("speed = 1",),
    ],
    ids=str,
)
def test_a_bad_setting_of_the_api_is_refused(layout, api):
    with pytest.raises(DeploymentError):
        read_node_config(write_config(layout, api=api))


def test_exactly_one_source_of_the_key(layout):
    path = write_config(layout, 'identity_signer = "s.sock"')
    with pytest.raises(DeploymentError, match="EXACTLY ONE"):
        read_node_config(path)
    text = path.read_text().replace('identity_key = "m0.key"\n', "").replace('identity_signer = "s.sock"\n', "")
    path.write_text(text)
    with pytest.raises(DeploymentError, match="EXACTLY ONE"):
        read_node_config(path)


def test_a_signer_needs_no_passphrase_in_the_node(layout):
    path = write_config(layout, 'identity_signer = "s.sock"', 'identity_passphrase_file = "p"')
    path.write_text(path.read_text().replace('identity_key = "m0.key"\n', ""))
    with pytest.raises(DeploymentError, match="BELONGS TO THE SIGNER"):
        read_node_config(path)


def test_a_signer_that_is_not_there_is_refused_at_the_start(layout):
    path = write_config(layout, 'identity_signer = "s.sock"')
    path.write_text(path.read_text().replace('identity_key = "m0.key"\n', ""))
    with pytest.raises(DeploymentError, match="REACH THE SIGNER"):
        read_node_config(path)


def test_a_config_reads_an_encrypted_key(layout):
    (layout / "m0.key").unlink()
    identity = Identity.create()
    identity.save(layout / "m0.key", b"words")
    (layout / "p").write_text("words\n")
    (layout / "p").chmod(0o600)
    config = read_node_config(write_config(layout, 'identity_passphrase_file = "p"'))
    assert config.identity.public_key == identity.public_key


def test_too_many_requests_get_429(layout):
    service = service_with(layout, api=("requests_per_second = 1", "burst = 2"))
    service.start()
    try:
        codes = []
        for _ in range(4):
            try:
                with urllib.request.urlopen(url(service), timeout=5) as answer:
                    codes.append(answer.status)
            except urllib.error.HTTPError as error:
                codes.append(error.code)
                if error.code == 429:
                    assert error.headers["Retry-After"] == "1"
        assert codes[:2] == [200, 200]
        assert 429 in codes[2:]
    finally:
        service.stop()


def test_health_is_not_limited(layout):
    service = service_with(layout, api=("requests_per_second = 1", "burst = 1"))
    service.start()
    try:
        for _ in range(5):
            with urllib.request.urlopen(url(service, path="/healthz"), timeout=5) as answer:
                assert answer.status == 200
    finally:
        service.stop()


def test_posts_are_limited_and_a_batch_costs_its_size(layout):
    service = service_with(layout, api=("requests_per_second = 1", "burst = 5"))
    service.start()
    try:
        client = Client(url(service, path=""))
        key = Identity.create()
        batch = [
            SignedTransfer.create(key, Transfer(key.identity_id, "bob", 1, nonce))
            for nonce in range(10)
        ]
        # An account with no funds, so refused: what counts here is the cost of the request.
        with pytest.raises(ApiError):
            client.submit_many(batch)
        with pytest.raises(ApiError) as caught:
            client.status()
        assert caught.value.status == 429
    finally:
        service.stop()


def test_connections_beyond_the_limit_are_closed(layout, monkeypatch):
    import network.service as service_module

    monkeypatch.setattr(service_module, "MAX_CONNECTIONS", 2)
    service = service_with(layout)
    service.start()
    held = []
    try:
        for _ in range(2):
            held.append(socket.create_connection(("127.0.0.1", service.api_address[1])))
        assert wait_until(lambda: service._api._places._value == 0, 5)
        extra = socket.create_connection(("127.0.0.1", service.api_address[1]))
        extra.settimeout(3)
        assert extra.recv(1) == b""
        extra.close()
        for connection in held:
            connection.close()
        assert wait_until(lambda: service._api._places._value == 2, 15)
    finally:
        for connection in held:
            connection.close()
        service.stop()


def test_the_metrics_count_votes_of_the_epoch(layout):
    service = service_with(layout)
    service.start()
    try:
        with urllib.request.urlopen(url(service, path="/metrics"), timeout=5) as answer:
            assert "psystem_epoch_votes 0" in answer.read().decode()
    finally:
        service.stop()


# Revocation.


def nodes_with_revocation(tmp_path, revoked_file=None, only_first=False, sync_interval=0.1, only_second=False):
    authority = create_authority(tmp_path / "ca")
    sender = Identity.create()
    genesis = State({sender.identity_id: 10})
    members = sorted((Identity.create() for _ in range(4)), key=lambda m: m.public_key)
    committee = Committee.create([m.public_key for m in members], 1, genesis)
    made = []
    for index in range(2):
        node_id = f"rev-{index}"
        tls = issue_node_certificate(authority, node_id, tmp_path / node_id)
        made.append(
            Node(
                node_id,
                genesis,
                quorum=QuorumConfig(
                    committee,
                    members[index],
                    tmp_path / f"{index}.sqlite",
                    create=True,
                    sync_interval=sync_interval,
                ),
                tls_config=replace(
                    tls,
                    revoked_file=(
                        None
                        if revoked_file is None
                        or (only_first and index > 0)
                        or (only_second and index == 0)
                        else str(revoked_file)
                    ),
                ),
            )
        )
    for node in made:
        node.start()
    return made


def link_ok(left, right):
    host, port = right.address()
    return left.connect_peer(Peer(node_id=right.node_id, host=host, port=port))


def fingerprint(node):
    return psystem("authority", "fingerprint", node.tls_config.certificate).strip()


def test_without_a_list_nobody_is_refused(tmp_path):
    left, right = nodes_with_revocation(tmp_path)
    try:
        assert link_ok(left, right)
    finally:
        left.stop()
        right.stop()


def test_a_revoked_peer_cannot_connect_in_either_direction(tmp_path):
    revoked = tmp_path / "revoked.txt"
    revoked.write_text("")
    left, right = nodes_with_revocation(tmp_path, revoked)
    try:
        revoked.write_text(f"# note\n{fingerprint(left)}  # lost laptop\n{fingerprint(right)}\n")
        assert not link_ok(left, right)
        assert not link_ok(right, left)
    finally:
        left.stop()
        right.stop()


def test_a_fingerprint_with_a_note_and_in_capitals_counts(tmp_path):
    # Alone in the list: in the test above another line can do the refusing by itself.
    revoked = tmp_path / "revoked.txt"
    revoked.write_text("")
    left, right = nodes_with_revocation(tmp_path, revoked, only_first=True)
    try:
        revoked.write_text(f"# note\n  {fingerprint(right).upper()}  # lost laptop\n")
        assert not link_ok(left, right)
    finally:
        left.stop()
        right.stop()


def test_who_dials_checks_the_list_by_itself(tmp_path):
    revoked = tmp_path / "revoked.txt"
    revoked.write_text("")
    left, right = nodes_with_revocation(tmp_path, revoked, only_first=True)
    try:
        revoked.write_text(f"{fingerprint(right)}\n")
        # Only the one that dials holds the list: the other accepts, and the dialer must say no.
        assert not link_ok(left, right)
    finally:
        left.stop()
        right.stop()


def test_who_listens_checks_the_list_by_itself(tmp_path):
    revoked = tmp_path / "revoked.txt"
    revoked.write_text("")
    # No sync loop: it closes revoked connections too, and would hide a listener that lets one in.
    # Only the listener holds the list, and the one with the lower id dials: the other way round the
    # listener dials back, and its check as a dialer would hide the one under test.
    left, right = nodes_with_revocation(tmp_path, revoked, sync_interval=None, only_second=True)
    assert left.node_id < right.node_id
    try:
        revoked.write_text(f"{fingerprint(left)}\n")
        link_ok(left, right)
        time.sleep(0.5)
        assert left.node_id not in right.peer_connections
    finally:
        left.stop()
        right.stop()


def test_a_listener_with_nothing_revoked_keeps_the_same_connection(tmp_path):
    # The control of the test above: what it sees there is the list, not something else.
    revoked = tmp_path / "revoked.txt"
    revoked.write_text("")
    left, right = nodes_with_revocation(tmp_path, revoked, sync_interval=None, only_second=True)
    try:
        link_ok(left, right)
        time.sleep(0.5)
        assert left.node_id in right.peer_connections
    finally:
        left.stop()
        right.stop()


def test_a_list_that_cannot_be_read_refuses_everyone(tmp_path):
    left, right = nodes_with_revocation(tmp_path, tmp_path / "missing.txt")
    try:
        assert not link_ok(left, right)
    finally:
        left.stop()
        right.stop()


@pytest.mark.filterwarnings("error::pytest.PytestUnhandledThreadExceptionWarning")
def test_a_connection_closed_during_the_check_does_not_stop_synchronization(tmp_path):
    revoked = tmp_path / "revoked.txt"
    revoked.write_text("")
    left, right = nodes_with_revocation(tmp_path, revoked)
    try:
        assert link_ok(left, right)
        assert wait_until(lambda: left.peer_connections, 10)
        connection = left.peer_connections[right.node_id]
        closed = connection.connection
        closed.close()

        class Stale:
            connection = closed
            node_id = "stale"

        left._close_revoked([Stale()])
        assert left._sync_thread.is_alive()
    finally:
        left.stop()
        right.stop()


@pytest.mark.filterwarnings("error::pytest.PytestUnhandledThreadExceptionWarning")
def test_a_revocation_closes_a_live_connection_with_no_restart(tmp_path):
    revoked = tmp_path / "revoked.txt"
    revoked.write_text("")
    left, right = nodes_with_revocation(tmp_path, revoked)
    try:
        assert link_ok(left, right)
        assert wait_until(lambda: left.peer_connections and right.peer_connections, 10)
        revoked.write_text(f"{fingerprint(right)}\n{fingerprint(left)}\n")
        assert wait_until(lambda: not left.peer_connections and not right.peer_connections, 10)
    finally:
        left.stop()
        right.stop()


def test_the_fingerprint_of_the_command_is_what_a_connection_sees(tmp_path):
    left, right = nodes_with_revocation(tmp_path)
    try:
        assert link_ok(left, right)
        assert wait_until(lambda: left.peer_connections, 10)
        stream = left.peer_connections[right.node_id].connection
        assert SecureTransport.certificate_fingerprint(stream) == fingerprint(right)
    finally:
        left.stop()
        right.stop()


@pytest.mark.parametrize(
    "start",
    [
        b"HTTP/1.1 200 OK\r\nContent-Length: 101\r\n\r\n",
        b"HTTP/1.1 500 Error\r\nContent-Length: 101\r\n\r\n",
        b"not http at all\r\n\r\n",
    ],
)
def test_a_node_that_dies_halfway_through_an_answer_is_a_failed_connection(start):
    # A long campaign of faults lost its traffic to this: what http.client raises is no OSError.
    listener = socket.create_server(("127.0.0.1", 0))

    def answer():
        connection, _ = listener.accept()
        connection.recv(65536)
        connection.sendall(start)
        connection.close()

    thread = threading.Thread(target=answer, daemon=True)
    thread.start()

    try:
        client = Client(f"http://127.0.0.1:{listener.getsockname()[1]}", timeout=5)
        with pytest.raises(OSError):
            client.status()
    finally:
        thread.join(5)
        listener.close()


def test_exhausted_tokens_return_structured_429(layout):
    service = service_with(layout, api=("requests_per_second = 1", "burst = 1"))
    service.start()
    try:
        urllib.request.urlopen(url(service), timeout=5).read()
        with pytest.raises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(url(service), timeout=5)
        assert caught.value.code == 429
        body = json.loads(caught.value.read())
        assert body == {"error": "TOO MANY REQUESTS"}
    finally:
        service.stop()


def test_invalid_token_returns_structured_401(layout):
    (layout / "token").write_text("a" * 32)
    (layout / "token").chmod(0o600)
    service = service_with(
        layout,
        api=('host = "127.0.0.1"', 'token_file = "token"'),
    )
    service.start()
    try:
        request = urllib.request.Request(
            url(service),
            headers={"Authorization": "Bearer " + "b" * 32},
        )
        with pytest.raises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=5)
        assert caught.value.code == 401
        body = json.loads(caught.value.read())
        assert isinstance(body, dict)
        assert body.get("error") == "TOKEN REQUIRED"
    finally:
        service.stop()
