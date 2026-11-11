"""The HTTP interface and the files of a deployment, in one process."""

import json
import stat
import urllib.error
import urllib.request

import pytest

from core.event import Transfer
from core.signed_event import SignedTransfer
from crypto.identity import Identity
from network.audit import AuditLog
from network.deployment import DeploymentError, parse_genesis, read_node_config, write_genesis
from network.node_tls_identity import create_authority, issue_node_certificate
from network.quorum import QuorumConfig
from network.service import JsonLogFormatter, MAX_BATCH, MAX_BODY_BYTES, Service
from sdk.client import ApiError, ChainVerifier, Client, Wallet, WalletError, signed_to_json


def key_pair(path):
    identity = Identity.create()
    identity.save(path)
    return identity


@pytest.fixture
def layout(tmp_path):
    authority = create_authority(tmp_path / "ca")
    issue_node_certificate(authority, "api-node", tmp_path)
    sender = Identity.create()
    members = [key_pair(tmp_path / f"m{i}.key") for i in range(4)]
    write_genesis(
        tmp_path / "genesis.json",
        [m.public_key for m in members],
        1,
        {sender.identity_id: 100},
    )
    return tmp_path, sender, members


def write_config(base, extra="", api='host = "127.0.0.1"\nport = 0', top=""):
    path = base / "node.toml"
    path.write_text(
        f'''node_id = "api-node"
host = "127.0.0.1"
port = 0
identity_key = "m0.key"
tls_certificate = "api-node.crt"
tls_key = "api-node.key"
tls_authority = "ca/ca.crt"
genesis = "genesis.json"
store = "votes.sqlite"
{top}
{extra}
[api]
{api}
'''
    )
    return path


@pytest.fixture
def service(layout):
    base, sender, members = layout
    running = Service(read_node_config(write_config(base)), create=True)
    running.start()
    yield running, sender, members
    running.stop()


def url(running) -> str:
    host, port = running.api_address
    return f"http://{host}:{port}"


def raw(running, method, path, body=None, headers=None):
    request = urllib.request.Request(url(running) + path, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def spend(sender, nonce=0, receiver="bob", amount=1) -> SignedTransfer:
    return SignedTransfer.create(sender, Transfer(sender.identity_id, receiver, amount, nonce))


# --- The interface ----------------------------------------------------------------------


def test_sdk_exposes_the_response_request_id(service):
    running, _, _ = service
    client = Client(url(running))
    client.status()
    assert client.last_request_id


def test_every_response_has_a_request_id_and_accepts_a_correlation_id(service):
    running, _, _ = service
    request = urllib.request.Request(
        url(running) + "/healthz", headers={"X-Request-ID": "client-42"}
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        assert json.loads(response.read()) == {"status": "ok"}
        assert response.headers["X-Request-ID"] == "client-42"

    request = urllib.request.Request(url(running) + "/v1/status")
    with urllib.request.urlopen(request, timeout=5) as response:
        assert response.headers["X-Request-ID"]


def test_status_says_what_an_operator_needs(service):
    running, _, _ = service
    status = Client(url(running)).status()
    assert status["api_version"] == "v1"
    assert status["node_id"] == "api-node"
    assert status["epoch"] == 0
    assert status["halted"] is False
    assert status["is_member"] is True
    assert status["genesis_hash"] == running.config.genesis.file_hash


def test_account_of_a_stranger_is_empty(service):
    running, _, _ = service
    assert Client(url(running)).account("nobody") == {
        "account": "nobody",
        "balance": 0,
        "next_nonce": 0,
    }


def test_healthz(service):
    running, _, _ = service
    assert raw(running, "GET", "/healthz")[0] == 200


def test_readyz_is_public_without_authentication(service):
    running, _, _ = service
    status, body = raw(running, "GET", "/readyz")
    assert status == 200
    assert json.loads(body) == {"status": "ready"}


def test_readyz_is_ready_after_start(service):
    running, _, _ = service
    status, body = raw(running, "GET", "/readyz")
    assert status == 200
    assert json.loads(body) == {"status": "ready"}


def test_readyz_says_503_when_halted(service):
    from network.message import encode_certificate
    from core.attestation import QuorumCertificate, Vote

    running, sender, members = service
    committee = running.config.genesis.committee
    ordered = sorted(members, key=lambda m: m.public_key)

    def certificate(receiver):
        event = spend(sender, 0, receiver).transfer
        return QuorumCertificate(
            event,
            tuple(Vote.create(committee, ordered[i], event) for i in range(3)),
        )

    running.node._handle_peer_message(encode_certificate(certificate("a")))
    running.node._handle_peer_message(encode_certificate(certificate("b")))

    status, body = raw(running, "GET", "/readyz")
    assert status == 503
    assert json.loads(body)["status"] == "not_ready"


def test_healthz_says_503_when_halted(service):
    from network.message import encode_certificate
    from core.attestation import QuorumCertificate, Vote

    running, sender, members = service
    committee = running.config.genesis.committee
    ordered = sorted(members, key=lambda m: m.public_key)

    def certificate(receiver):
        event = spend(sender, 0, receiver).transfer
        return QuorumCertificate(
            event,
            tuple(Vote.create(committee, ordered[i], event) for i in range(3)),
        )

    running.node._handle_peer_message(encode_certificate(certificate("a")))
    running.node._handle_peer_message(encode_certificate(certificate("b")))

    status, body = raw(running, "GET", "/healthz")
    assert status == 503
    assert json.loads(body)["status"] == "halted"
    details = Client(url(running)).status()
    assert details["halted"] and details["conflicted"]
    assert len(details["guilty_members"]) == 3


def test_metrics_are_in_the_text_format(service):
    running, sender, _ = service
    Client(url(running)).submit(spend(sender))
    status, body = raw(running, "GET", "/metrics")
    text = body.decode()
    assert status == 200
    assert "# TYPE psystem_executed_events gauge" in text
    assert "psystem_halted 0" in text
    assert "psystem_store_commits_total 1" in text


def test_metrics_expose_nonce_locked_permanently_counter(service):
    running, _, _ = service
    status, body = raw(running, "GET", "/metrics")
    text = body.decode()
    assert status == 200
    assert "# TYPE psystem_nonce_locked_permanently_total counter" in text
    assert "psystem_nonce_locked_permanently_total 0" in text
    for line in text.splitlines():
        assert line.startswith("#") or len(line.split(" ")) == 2


def test_transfer_is_accepted_with_202_and_gets_no_final_answer(service):
    running, sender, _ = service
    signed = spend(sender)
    response = Client(url(running)).submit(signed)
    assert response == {"accepted": True, "event_ids": [signed.transfer.event_id()]}
    # Alone, this node has one vote out of three. Accepted is not executed.
    assert Client(url(running)).certificate(signed.transfer.event_id()) is None


@pytest.mark.parametrize(
    "mutate",
    [
        lambda b: b.pop("signature"),
        lambda b: b.update(signature="zz"),
        lambda b: b.update(extra=1),
        lambda b: b["transfer"].update(amount=-1),
        lambda b: b["transfer"].update(amount=True),
        lambda b: b["transfer"].pop("nonce"),
    ],
)
def test_malformed_transfer_is_400(service, mutate):
    running, sender, _ = service
    body = signed_to_json(spend(sender))
    mutate(body)
    status, _ = raw(running, "POST", "/v1/transfers", json.dumps(body).encode())
    assert status == 400


def test_transfer_with_a_bad_signature_is_409(service):
    running, sender, _ = service
    body = signed_to_json(spend(sender))
    body["signature"] = "00" * 64
    status, _ = raw(running, "POST", "/v1/transfers", json.dumps(body).encode())
    assert status == 409


def test_conflicting_transfer_is_409(service):
    running, sender, _ = service
    client = Client(url(running))
    client.submit(spend(sender, 0, "bob"))
    with pytest.raises(ApiError) as error:
        client.submit(spend(sender, 0, "carol"))
    assert error.value.status == 409


@pytest.mark.parametrize(
    "body",
    [b"not json", b"[" * 200_000],
)
def test_body_that_is_not_json_is_400(service, body):
    running, _, _ = service
    status, _ = raw(running, "POST", "/v1/transfers", body)
    assert status == 400


def test_body_too_large_is_413(service):
    running, _, _ = service
    status, _ = raw(running, "POST", "/v1/transfers", b"x" * (MAX_BODY_BYTES + 1))
    assert status == 413


def test_batch_limits(service):
    running, sender, _ = service
    status, _ = raw(running, "POST", "/v1/transfers:batch", b"[]")
    assert status == 400
    many = json.dumps([signed_to_json(spend(sender, n)) for n in range(MAX_BATCH + 1)]).encode()
    status, _ = raw(running, "POST", "/v1/transfers:batch", many)
    assert status == 400
    status, _ = raw(running, "POST", "/v1/transfers:batch", b'{"a": 1}')
    assert status == 400


def test_batch_shares_one_write(service):
    running, sender, _ = service
    store = running.node._quorum._store
    before = store.commits
    Client(url(running)).submit_many([spend(sender, n) for n in range(10)])
    assert store.commits == before + 1


@pytest.mark.parametrize("path", ["/", "/v2/status", "/v1/nope", "/v1/accounts", "/v1/certificates/a/b"])
def test_unknown_path_is_404(service, path):
    running, _, _ = service
    assert raw(running, "GET", path)[0] == 404


def test_invalid_event_id_is_400(service):
    running, _, _ = service
    assert raw(running, "GET", "/v1/certificates/nope")[0] == 400


def test_token_protects_everything_but_healthz(layout):
    base, sender, _ = layout
    token = base / "token"
    token.write_text("a" * 32)
    token.chmod(stat.S_IRUSR | stat.S_IWUSR)
    running = Service(
        read_node_config(write_config(base, api='port = 0\ntoken_file = "token"')),
        create=True,
    )
    running.start()
    try:
        assert raw(running, "GET", "/healthz")[0] == 200
        assert raw(running, "GET", "/v1/status")[0] == 401
        assert raw(running, "GET", "/metrics")[0] == 401
        assert raw(running, "POST", "/v1/transfers", b"{}")[0] == 401
        bad = {"Authorization": "Bearer " + "b" * 32}
        assert raw(running, "GET", "/v1/status", headers=bad)[0] == 401
        assert Client(url(running), "a" * 32).status()["node_id"] == "api-node"
    finally:
        running.stop()


# --- Files of a deployment --------------------------------------------------------------


GENESIS_KEYS = [bytes([i]) * 32 for i in (1, 2, 3, 4)]


def genesis_text(**changes):
    data = {
        "version": 1,
        "balances": {"alice": 5},
        "members": [key.hex() for key in GENESIS_KEYS],
        "f": 1,
    }
    data.update(changes)
    return json.dumps(data)


def test_genesis_hash_is_the_hash_of_the_file():
    import hashlib

    text = genesis_text()
    assert parse_genesis(text).file_hash == hashlib.sha256(text.encode()).hexdigest()


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "[]",
        genesis_text(version=2),
        genesis_text(unknown=1),
        genesis_text(f=2),
        genesis_text(balances={"alice": -1}),
        genesis_text(balances={"": 1}),
        genesis_text(balances={"alice": True}),
        genesis_text(balances=[]),
        genesis_text(members=["zz"]),
        genesis_text(governance={"members": ["aa" * 32], "threshold": 1}),
        genesis_text(governance={"threshold": 2}),
        json.dumps({"version": 1}),
    ],
)
def test_genesis_refuses_what_it_cannot_use(text):
    with pytest.raises(DeploymentError):
        parse_genesis(text)


def test_genesis_refuses_a_committee_that_is_not_3f_plus_1(tmp_path):
    with pytest.raises(DeploymentError):
        write_genesis(tmp_path / "g.json", GENESIS_KEYS[:3], 1, {})
    assert not (tmp_path / "g.json").exists()


@pytest.mark.parametrize(
    "top,api,reason",
    [
        ("typo_setting = 1", 'port = 0', "UNKNOWN"),
        ("sync_interval = 0", 'port = 0', "sync_interval"),
        ("sync_interval = -1", 'port = 0', "sync_interval"),
        ('joining = "yes"', 'port = 0', "joining"),
        ("", 'port = 70000', "PORT"),
        ("", 'bad = 1', "UNKNOWN"),
        ("", 'host = "0.0.0.0"\nport = 0', "token_file"),
    ],
)
def test_configuration_refuses_what_it_does_not_recognize(layout, top, api, reason):
    base, _, _ = layout
    with pytest.raises(DeploymentError, match=reason):
        read_node_config(write_config(base, top=top, api=api))


def test_configuration_refuses_unknown_limits(layout):
    base, _, _ = layout
    with pytest.raises(DeploymentError):
        read_node_config(write_config(base, extra="[limits]\nnope = 1"))


def test_configuration_refuses_a_key_others_can_read(layout):
    base, _, _ = layout
    (base / "m0.key").chmod(0o644)
    with pytest.raises(DeploymentError, match="READABLE"):
        read_node_config(write_config(base))


def test_configuration_refuses_a_token_others_can_read(layout):
    base, _, _ = layout
    (base / "token").write_text("a" * 32)
    (base / "token").chmod(0o644)
    with pytest.raises(DeploymentError, match="READABLE"):
        read_node_config(write_config(base, api='port = 0\ntoken_file = "token"'))


def test_configuration_refuses_a_short_token(layout):
    base, _, _ = layout
    (base / "token").write_text("short")
    (base / "token").chmod(0o600)
    with pytest.raises(DeploymentError, match="SHORT"):
        read_node_config(write_config(base, api='port = 0\ntoken_file = "token"'))


def test_a_store_is_not_created_without_being_asked(layout):
    from network.quorum import VoteStoreError

    base, _, _ = layout
    with pytest.raises(VoteStoreError):
        Service(read_node_config(write_config(base)), create=False)


def test_key_files(tmp_path):
    identity = Identity.create()
    path = tmp_path / "k.key"
    identity.save(path)
    assert Identity.load(path).public_key == identity.public_key
    assert path.stat().st_mode & 0o077 == 0
    with pytest.raises(FileExistsError):
        identity.save(path)
    (tmp_path / "other.key").write_text("nope")
    (tmp_path / "other.key").chmod(0o600)
    with pytest.raises(ValueError):
        Identity.load(tmp_path / "other.key")


def test_a_log_line_is_one_json_object_with_its_fields():
    import logging

    record = logging.LogRecord("psystem.x", logging.WARNING, "f", 1, "hello %s", ("you",), None)
    record.epoch = 3
    data = json.loads(JsonLogFormatter().format(record))
    assert data["message"] == "hello you"
    assert data["level"] == "WARNING"
    assert data["epoch"] == 3


# --- Limits on what a node takes ---------------------------------------------------------


def test_snapshots_are_off_unless_asked_for(layout):
    base = layout[0] if isinstance(layout, tuple) else layout
    config = read_node_config(write_config(base))
    assert config.snapshot_every is None
    assert config.prune is False
    assert config.quorum(False).snapshot_every is None


def test_snapshot_settings_reach_the_node(layout):
    base = layout[0] if isinstance(layout, tuple) else layout
    config = read_node_config(write_config(base, extra="[snapshots]\nevery = 100\nprune = true"))
    assert config.snapshot_every == 100
    assert config.prune is True
    quorum = config.quorum(False)
    assert quorum.snapshot_every == 100
    assert quorum.prune is True


@pytest.mark.parametrize(
    "extra",
    [
        "[snapshots]\nnope = 1",
        "[snapshots]\nevery = 0",
        "[snapshots]\nevery = \"10\"",
        "[snapshots]\nprune = true",
        "[snapshots]\nevery = 5\nprune = 1",
    ],
)
def test_bad_snapshot_settings_are_refused(layout, extra):
    base = layout[0] if isinstance(layout, tuple) else layout
    with pytest.raises(DeploymentError):
        read_node_config(write_config(base, extra=extra))


def limited(tmp_path, **limits):
    from network.quorum import QuorumRuntime

    members = sorted((Identity.create() for _ in range(4)), key=lambda m: m.public_key)
    sender = Identity.create()
    from core.attestation import Committee
    from core.state import State

    genesis = State({sender.identity_id: 10})
    committee = Committee.create([m.public_key for m in members], 1, genesis)
    return (
        QuorumRuntime(
            QuorumConfig(committee, members[0], tmp_path / "x.sqlite", create=True, **limits),
            genesis,
        ),
        sender,
    )


def test_a_sender_with_no_funds_gets_no_vote_and_leaves_no_trace(tmp_path):
    from network.message import encode_vote_request

    run, _ = limited(tmp_path, require_funds=True)
    stranger = Identity.create()
    output = run.driver.handle_message(encode_vote_request(spend(stranger)))
    assert output.replies == ()
    assert run.replica.votes() == []
    assert run.driver.signed_events == {}
    run.close()


def test_a_nonce_too_far_ahead_gets_no_vote(tmp_path):
    from network.message import encode_vote_request

    run, sender = limited(tmp_path, max_nonce_ahead=2)
    assert run.driver.handle_message(encode_vote_request(spend(sender, 2))).replies
    assert not run.driver.handle_message(encode_vote_request(spend(sender, 3))).replies
    run.close()


def test_evidence_kept_in_memory_has_a_limit(tmp_path):
    from network.message import encode_vote_request

    run, sender = limited(tmp_path, max_evidence=2)
    for nonce in range(5):
        run.driver.handle_message(encode_vote_request(spend(sender, nonce)))
    assert len(run.driver.signed_events) == 2
    # The votes do not depend on it.
    assert len(run.replica.votes()) == 5
    run.close()


def test_a_limit_refuses_only_a_vote_and_never_a_certificate(tmp_path):
    # A certified event must run on every node, whatever each one would have voted. A certificate
    # beyond the window is left out for now, and it runs when it comes back: as synchronization does.
    from core.attestation import QuorumCertificate, Vote
    from network.message import encode_certificate
    from network.quorum import QuorumRuntime

    members = sorted((Identity.create() for _ in range(4)), key=lambda m: m.public_key)
    sender = Identity.create()
    from core.attestation import Committee
    from core.state import State

    genesis = State({sender.identity_id: 10})
    committee = Committee.create([m.public_key for m in members], 1, genesis)
    run = QuorumRuntime(
        QuorumConfig(
            committee,
            members[0],
            tmp_path / "x.sqlite",
            create=True,
            max_nonce_ahead=0,
            require_funds=True,
        ),
        genesis,
    )
    for nonce in (1, 0, 1):
        event = spend(sender, nonce).transfer
        run.driver.handle_message(
            encode_certificate(
                QuorumCertificate(
                    event,
                    tuple(Vote.create(committee, members[i], event) for i in range(committee.n)),
                )
            )
        )
    assert [event.nonce for event in run.replica.executed] == [0, 1]
    assert run.driver.certificates_left_out == 1
    run.close()


# --- The wallet ---------------------------------------------------------------------------


@pytest.fixture
def wallet(tmp_path):
    made = Wallet(Identity.create(), tmp_path / "wallet.sqlite")
    yield made
    made.close()


def test_a_wallet_uses_nonces_in_order(wallet):
    assert [wallet.transfer("bob", 1).transfer.nonce for _ in range(3)] == [0, 1, 2]


def test_a_wallet_refuses_a_second_event_for_a_nonce(wallet):
    wallet.transfer("bob", 1, nonce=0)
    with pytest.raises(WalletError):
        wallet.transfer("carol", 1, nonce=0)


def test_the_same_event_again_gives_the_same_signature(wallet):
    first = wallet.transfer("bob", 1, nonce=0)
    assert wallet.transfer("bob", 1, nonce=0) == first


def test_a_wallet_remembers_after_a_restart(tmp_path):
    identity = Identity.create()
    first = Wallet(identity, tmp_path / "w.sqlite")
    signed = first.transfer("bob", 1)
    first.close()

    second = Wallet(identity, tmp_path / "w.sqlite")
    with pytest.raises(WalletError):
        second.transfer("carol", 1, nonce=0)
    assert second.next_nonce() == 1
    assert second.unfinished(0) == [signed]
    assert second.unfinished(1) == []
    second.close()


def test_the_event_is_on_disk_before_it_is_signed(tmp_path, monkeypatch):
    # If the write fails there must be no signature to send.
    identity = Identity.create()
    wallet = Wallet(identity, tmp_path / "w.sqlite")

    class Failing:
        def __init__(self, inner):
            self.inner = inner
            self.in_transaction = False

        def execute(self, statement, *args):
            import sqlite3

            if statement.startswith("INSERT"):
                raise sqlite3.OperationalError("disk full")
            return self.inner.execute(statement, *args)

        def __getattr__(self, name):
            return getattr(self.inner, name)

    wallet._connection = Failing(wallet._connection)
    with pytest.raises(WalletError):
        wallet.transfer("bob", 1)


def test_a_journal_from_before_accounts_of_another_key_is_refused(tmp_path):
    # A journal made by an earlier version names only its key.
    import sqlite3

    Wallet(Identity.create(), tmp_path / "j").close()
    connection = sqlite3.connect(tmp_path / "j")
    connection.execute("DROP TABLE journal_account")
    connection.commit()
    connection.close()
    with pytest.raises(WalletError, match="ANOTHER KEY"):
        Wallet(Identity.create(), tmp_path / "j")


def test_a_journal_of_another_key_is_refused(tmp_path):
    first = Wallet(Identity.create(), tmp_path / "w.sqlite")
    first.close()
    with pytest.raises(WalletError):
        Wallet(Identity.create(), tmp_path / "w.sqlite")


# --- A client against a node that lies --------------------------------------------------


class LyingClient(Client):
    def __init__(self, answers):
        super().__init__("http://unused")
        self.answers = answers

    def _request(self, method, path, body=None):
        for prefix, answer in self.answers.items():
            if path.startswith(prefix):
                return answer
        raise ApiError(404, {})


def _verifier():
    from core.attestation import Committee
    from core.state import State

    members = sorted((Identity.create() for _ in range(4)), key=lambda m: m.public_key)
    committee = Committee.create([m.public_key for m in members], 1, State({"alice": 5}))
    return members, committee, ChainVerifier(committee, None)


def test_a_valid_certificate_is_final_whatever_the_node_is():
    from core.attestation import QuorumCertificate, Vote
    from network.message import encode_certificate

    members, committee, verifier = _verifier()
    event = Transfer("alice", "bob", 1, 0)
    good = QuorumCertificate(event, tuple(Vote.create(committee, members[i], event) for i in range(committee.n)))
    client = LyingClient({"/v1/certificates": encode_certificate(good), "/v1/closures": {"closures": []}})
    assert client.verify_final(event, verifier)


def test_a_node_cannot_prove_what_was_not_certified():
    from core.attestation import QuorumCertificate, Vote
    from network.message import encode_certificate

    members, committee, verifier = _verifier()
    event = Transfer("alice", "bob", 1, 0)
    one_signature = Vote.create(committee, members[0], event).signature
    forged = QuorumCertificate(event, tuple(Vote(i, one_signature) for i in range(3)))
    client = LyingClient({"/v1/certificates": encode_certificate(forged), "/v1/closures": {"closures": []}})
    assert not client.verify_final(event, verifier)


def test_a_certificate_for_another_event_proves_nothing():
    from core.attestation import QuorumCertificate, Vote
    from network.message import encode_certificate

    members, committee, verifier = _verifier()
    other = Transfer("alice", "carol", 1, 0)
    valid = QuorumCertificate(other, tuple(Vote.create(committee, members[i], other) for i in range(3)))
    client = LyingClient({"/v1/certificates": encode_certificate(valid), "/v1/closures": {"closures": []}})
    assert not client.verify_final(Transfer("alice", "bob", 1, 0), verifier)


def test_garbage_from_a_node_proves_nothing():
    _, _, verifier = _verifier()
    client = LyingClient({"/v1/certificates": {"type": "nope"}, "/v1/closures": {"closures": []}})
    assert not client.verify_final(Transfer("alice", "bob", 1, 0), verifier)


def test_a_forged_closure_is_refused_by_the_verifier():
    _, _, verifier = _verifier()
    with pytest.raises(ValueError):
        verifier.add_closures([{"change": 1}])
    assert verifier.current.epoch == 0


def test_a_certificate_of_an_unknown_epoch_is_not_verified():
    from core.attestation import QuorumCertificate

    _, _, verifier = _verifier()
    assert not verifier.verify(QuorumCertificate(Transfer("a", "b", 1, 0), (), 5))




def test_a_closure_that_does_not_verify_is_refused_by_the_verifier():
    from core.attestation import EpochChange, EpochClosure, Governance
    from network.message import encode_epoch_closure

    _, committee, _ = _verifier()
    signers = [Identity.create() for _ in range(2)]
    governance = Governance(tuple(sorted(s.public_key for s in signers)), 2)
    verifier = ChainVerifier(committee, governance)
    change = EpochChange.create(committee, committee.members, 1, governance, signers)
    # Well formed, ordered by governance, and with no report and no vote of the committee.
    closure = EpochClosure(change, ())
    with pytest.raises(ValueError):
        verifier.add_closures([encode_epoch_closure(closure)["closure"]])
    assert verifier.current.epoch == 0


def test_init_store_creates_once(layout):
    from network.cli import main

    base, _, _ = layout
    config = write_config(base)
    assert main(["init-store", "--config", str(config)]) == 0
    assert (base / "votes.sqlite").exists()
    assert main(["init-store", "--config", str(config)]) == 2
    # And a node starts from it without being told to create anything.
    running = Service(read_node_config(config))
    running.start()
    running.stop()


def test_the_audit_log_records_start_an_unauthorized_call_and_stop(layout):
    base, _, _ = layout
    (base / "token").write_text("a" * 32)
    (base / "token").chmod(0o600)
    running = Service(
        read_node_config(
            write_config(base, api='host = "127.0.0.1"\nport = 0\ntoken_file = "token"')
        ),
        create=True,
    )
    running.start()

    try:
        assert raw(running, "GET", "/v1/status")[0] == 401
    finally:
        running.stop()

    path = base / "votes.sqlite.audit.jsonl"
    assert AuditLog.verify(path) == 3
    actions = [json.loads(line)["action"] for line in path.read_text().splitlines()]
    assert actions == ["service.started", "api.unauthorized", "service.stopped"]


def test_the_audit_log_records_a_rate_limited_request(layout):
    base, _, _ = layout
    running = Service(
        read_node_config(
            write_config(
                base,
                api='host = "127.0.0.1"\nport = 0\nrequests_per_second = 0.01\nburst = 1',
            )
        ),
        create=True,
    )
    running.start()

    try:
        assert raw(running, "GET", "/metrics")[0] == 200
        assert raw(running, "GET", "/metrics")[0] == 429
    finally:
        running.stop()

    path = base / "votes.sqlite.audit.jsonl"
    actions = [json.loads(line)["action"] for line in path.read_text().splitlines()]
    assert actions == ["service.started", "api.rate_limited", "service.stopped"]
    assert AuditLog.verify(path) == 3
