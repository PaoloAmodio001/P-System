"""Supply conservation of assets, where the model puts it: in `auth`.

`asset_supply_conserved` (formal/lean/PSystem/QuorumAssets.lean) takes as hypothesis that every event stays
inside the accounts of one asset or out of them. In the model that is a rule of `auth`, so of the vote:
derivation and execution do not look at assets. An honest node gives no vote to an event that crosses
assets, and refuses it as it refuses any other vote, with no exception. The API refuses it first, with
its reason (422).

Before this, the check raised SupplyViolation inside the vote and inside the execution of a certificate.
A node that received a valid certificate for such an event raised instead of running it, which Lean does
(tests/test_assets_differential.py), and a submit raised out of the driver.
"""

import json
import urllib.error
import urllib.request

import pytest

from core.attestation import Committee, QuorumCertificate, Vote, stays_in_one_asset
from core.derive import StateDeriver, check_supply_conservation
from core.event import Transfer
from core.exceptions import SupplyViolation
from core.signed_event import SignedTransfer
from core.state import State, asset_account, asset_id
from crypto.identity import Identity
from network.message import encode_vote_request
from network.quorum import QuorumConfig, QuorumReplica, QuorumRuntime, SqliteVoteStore

ISSUER = Identity.create()
ALICE = Identity.create()
COIN = asset_id(ISSUER.identity_id, "coin", 1000)
OTHER = asset_id(ISSUER.identity_id, "other", 500)
MEMBERS = sorted((Identity.create() for _ in range(4)), key=lambda m: m.public_key)
COMMITTEE = Committee.create([m.public_key for m in MEMBERS], 1, State())


def account(identity, asset):
    return asset_account(identity.identity_id, asset)


CROSS = Transfer(account(ISSUER, COIN), account(ALICE, OTHER), 10, 0)
SAME = Transfer(account(ISSUER, COIN), account(ALICE, COIN), 10, 0)


@pytest.fixture
def runtime(tmp_path):
    made = QuorumRuntime(QuorumConfig(COMMITTEE, MEMBERS[0], tmp_path / "v.sqlite", create=True), State())
    yield made
    made.close()


def test_the_rule_on_its_own():
    assert not stays_in_one_asset(CROSS)
    assert stays_in_one_asset(SAME)
    assert stays_in_one_asset(Transfer("alice", "bob", 1, 0))

    with pytest.raises(SupplyViolation) as error:
        check_supply_conservation(CROSS)

    assert error.value.violated == {COIN: -10, OTHER: 10} and error.value.delta == 10
    check_supply_conservation(SAME)


def test_a_submit_that_crosses_assets_gets_no_vote_and_raises_nothing(runtime):
    output = runtime.submit_group([SignedTransfer.create(ISSUER, CROSS)])

    assert output.broadcasts == ()
    assert runtime.replica.votes() == []


def test_a_request_from_a_peer_that_crosses_assets_gets_no_vote(runtime):
    output, error = runtime.handle_group([encode_vote_request(SignedTransfer.create(ISSUER, CROSS))])

    assert error is None and output.replies == ()
    assert runtime.replica.votes() == []


def test_the_auth_of_the_node_refuses_it_even_without_the_signature_check(runtime):
    # The replica of a node, given the event directly: its `auth` is the rule.
    assert runtime.replica.handle_vote_request(CROSS) is None
    assert runtime.replica.handle_vote_request(SAME) is not None


def test_execution_follows_the_model_and_does_not_look_at_assets(tmp_path):
    # As in Lean: a valid certificate runs if the state allows it. Only more than `f` faulty make one.
    genesis = State({account(ISSUER, COIN): 1000})
    committee = Committee.create([m.public_key for m in MEMBERS], 1, genesis)
    store = SqliteVoteStore(tmp_path / "e.sqlite", committee, MEMBERS[0].public_key, create=True)
    replica = QuorumReplica(MEMBERS[0], genesis, store, lambda _event: True)
    certificate = QuorumCertificate(CROSS, tuple(Vote.create(committee, m, CROSS) for m in MEMBERS[:3]), 0)

    assert replica.handle_certificate(certificate)
    assert replica.state.balance(account(ALICE, OTHER)) == 10
    assert StateDeriver.apply_events(genesis, [CROSS]).balance(account(ALICE, OTHER)) == 10
    store.close()


def test_the_api_refuses_it_with_its_reason(tmp_path):
    from network.deployment import read_node_config, write_genesis
    from network.node_tls_identity import create_authority, issue_node_certificate
    from network.service import Service
    from tests.test_service import url, write_config

    authority = create_authority(tmp_path / "ca")
    issue_node_certificate(authority, "api-node", tmp_path)
    members = []
    for i in range(4):
        member = Identity.create()
        member.save(tmp_path / f"m{i}.key")
        members.append(member)
    write_genesis(tmp_path / "genesis.json", [m.public_key for m in members], 1, {})
    running = Service(read_node_config(write_config(tmp_path)), create=True)
    running.start()

    try:
        signed = SignedTransfer.create(ISSUER, CROSS)
        body = json.dumps(
            {
                "transfer": {
                    "sender": CROSS.sender,
                    "receiver": CROSS.receiver,
                    "amount": CROSS.amount,
                    "nonce": CROSS.nonce,
                    "parents": [],
                },
                "public_key": signed.public_key.hex(),
                "signature": signed.signature.hex(),
            }
        ).encode()
        request = urllib.request.Request(
            url(running) + "/v1/transfers",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )

        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request, timeout=5)

        assert error.value.code == 422
        assert json.loads(error.value.read())["error"] == "SUPPLY_VIOLATION"
    finally:
        running.stop()
