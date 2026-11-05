"""Four real processes, on real TLS, made and run with the `psystem` command.

Until this test existed the system had only ever run inside one process, and it could not have
run in any other way. SIGKILL here is a real death of a real node with its connections open.

The checks are properties of each run: EMPIRICAL, for n = 4, f = 1, on one machine.
"""

import json

import pytest

from core.attestation import Committee, EpochChange
from core.event import Transfer
from core.signed_event import SignedTransfer
from core.state import State
from crypto.identity import Identity
from network.deployment import read_genesis
from sdk.client import ApiError, ChainVerifier, Client, Wallet
from tests.deployment_helpers import Deployment, psystem, wait_until


@pytest.fixture
def cluster(tmp_path):
    deployment = Deployment(tmp_path)
    deployment.start_all()
    yield deployment
    deployment.stop_all()


def clients(deployment):
    return [Client(deployment.api_url(i)) for i in range(deployment.count)]


def connected(deployment, minimum: int) -> bool:
    return all(
        len(client.status()["peers"]) >= minimum
        for client in clients(deployment)
    )


def wallet(deployment) -> Wallet:
    return Wallet(Identity.load(deployment.sender_key), deployment.base / "wallet.sqlite")


def verifier(deployment) -> ChainVerifier:
    genesis = read_genesis(deployment.base / "genesis.json")
    return ChainVerifier(genesis.committee, genesis.governance)


def same_state(client_list) -> bool:
    return len({client.status()["state_root"] for client in client_list}) == 1


def test_a_deployment_made_with_the_command_executes_a_transfer(cluster):
    api = clients(cluster)
    assert wait_until(lambda: connected(cluster, 3))
    assert len({client.status()["genesis_hash"] for client in api}) == 1
    money = wallet(cluster)
    signed = money.transfer("bob", 8)

    assert api[0].submit(signed)["accepted"]
    assert api[3].wait_final(signed.transfer, verifier(cluster))
    assert wait_until(lambda: all(c.account("bob")["balance"] == 8 for c in api))
    assert wait_until(lambda: same_state(api))
    assert api[1].account(money.account)["next_nonce"] == 1


def test_sigterm_stops_a_node_cleanly(cluster):
    assert cluster.stop(0) == 0
    lines = cluster.log_lines(0)
    assert any(line["message"] == "node stopped" for line in lines)
    assert all("time" in line and "level" in line for line in lines)


def test_a_node_killed_by_sigkill_comes_back_with_its_log_and_catches_up(cluster):
    api = clients(cluster)
    assert wait_until(lambda: connected(cluster, 3))
    money = wallet(cluster)
    events = [money.transfer("bob", 1) for _ in range(5)]
    api[0].submit_many(events)
    assert wait_until(lambda: all(c.status()["executed"] == 5 for c in api))
    before = api[3].status()["state_root"]

    cluster.kill(3)
    later = [money.transfer("carol", 1) for _ in range(5)]
    api[0].submit_many(later)
    assert wait_until(lambda: all(c.status()["executed"] == 10 for c in api[:3]))

    cluster.start(3, create=False)
    assert api[3].status()["executed"] >= 5
    assert api[3].status()["state_root"] == before or api[3].status()["executed"] > 5
    assert wait_until(lambda: api[3].status()["executed"] == 10)
    assert wait_until(lambda: same_state(api))
    assert not any(client.status()["halted"] for client in api)


def test_a_deleted_store_is_refused_instead_of_voting_again(cluster):
    assert wait_until(lambda: connected(cluster, 3))
    cluster.kill(2)
    cluster.store(2).unlink()

    with pytest.raises(AssertionError):
        # Without --create-store it never comes up: a validator with no votes must not start
        # by itself. The helper reads the line it prints when it is up, and gets nothing.
        try:
            cluster.start(2, create=False)
        except json.JSONDecodeError as error:
            raise AssertionError from error

    cluster.processes.pop(2).wait(timeout=10)


def test_a_quorum_works_with_one_node_dead(cluster):
    api = clients(cluster)
    assert wait_until(lambda: connected(cluster, 3))
    cluster.kill(1)
    money = wallet(cluster)
    signed = money.transfer("bob", 3)
    assert api[0].submit(signed)["accepted"]
    assert api[2].wait_final(signed.transfer, verifier(cluster))


def test_with_two_nodes_dead_nothing_is_certified_and_nothing_breaks(cluster):
    # f = 1: no quorum, so no progress. That is the expected answer, and the event finishes
    # when a node returns and it is sent again.
    api = clients(cluster)
    assert wait_until(lambda: connected(cluster, 3))
    cluster.kill(1)
    cluster.kill(2)
    money = wallet(cluster)
    signed = money.transfer("bob", 3)
    assert api[0].submit(signed)["accepted"]
    assert not api[0].wait_final(signed.transfer, verifier(cluster), seconds=1.5)

    cluster.start(1, create=False)
    assert wait_until(lambda: "node-1" in api[0].status()["peers"])
    api[0].submit(signed)
    assert api[0].wait_final(signed.transfer, verifier(cluster))


def test_equivocation_through_the_api_gives_one_event_at_most(cluster):
    api = clients(cluster)
    assert wait_until(lambda: connected(cluster, 3))
    key = Identity.load(cluster.sender_key)
    first = SignedTransfer.create(key, Transfer(key.identity_id, "first", 1, 0))
    second = SignedTransfer.create(key, Transfer(key.identity_id, "second", 1, 0))
    outcomes = []

    for client, event in zip(api, (first, second, first, second)):
        try:
            outcomes.append(client.submit(event)["accepted"])
        except ApiError as error:
            outcomes.append(error.status)

    balances = lambda: [
        (c.account("first")["balance"], c.account("second")["balance"]) for c in api
    ]
    wait_until(lambda: any(sum(b) for b in balances()), seconds=3)

    for first_balance, second_balance in balances():
        assert first_balance == 0 or second_balance == 0

    assert not any(client.status()["halted"] for client in api)


def _change(deployment, keys) -> EpochChange:
    genesis = read_genesis(deployment.base / "genesis.json")
    return EpochChange.create(
        genesis.committee,
        keys,
        1,
        genesis.governance,
        [Identity.load(path) for path in deployment.governance_keys[:2]],
    )


def _encode_change(change: EpochChange) -> dict:
    from network.message import encode_epoch_change

    return encode_epoch_change(change)["change"]


def test_an_epoch_change_over_the_api_and_a_restart_afterwards(cluster):
    api = clients(cluster)
    assert wait_until(lambda: connected(cluster, 3))
    money = wallet(cluster)
    first = money.transfer("bob", 1)
    api[0].submit(first)
    assert wait_until(lambda: all(c.status()["executed"] == 1 for c in api))

    keys = [bytes.fromhex(member["public_key"]) for member in cluster.members]
    change = _change(cluster, keys)
    response = api[0]._request("POST", "/v1/epoch-changes", _encode_change(change))
    assert response["accepted"]
    assert wait_until(lambda: all(c.status()["epoch"] == 1 for c in api))

    # The old alternative is locked for good: the lock came from the reports.
    key = Identity.load(cluster.sender_key)
    other = SignedTransfer.create(key, Transfer(key.identity_id, "mallory", 1, 0))
    with pytest.raises(ApiError):
        api[1].submit(other)

    second = money.transfer("bob", 1)
    api[1].submit(second)
    chain = verifier(cluster)
    assert api[2].wait_final(second.transfer, chain)
    assert chain.current.epoch == 1

    cluster.kill(3)
    cluster.start(3, create=False)
    assert api[3].status()["epoch"] == 1
    assert wait_until(lambda: api[3].status()["executed"] == 2)
    assert wait_until(lambda: same_state(api))
    assert any(
        line["message"] == "new epoch installed"
        for line in cluster.log_lines(0)
    )


def test_a_restored_backup_votes_for_nothing_until_the_next_epoch(cluster):
    api = clients(cluster)
    assert wait_until(lambda: connected(cluster, 3))
    money = wallet(cluster)
    api[0].submit(money.transfer("bob", 1))
    assert wait_until(lambda: all(c.status()["executed"] == 1 for c in api))

    backup = cluster.base / "backup.sqlite"
    psystem("backup", str(cluster.store(3)), "--out", str(backup))
    api[0].submit(money.transfer("bob", 1))
    assert wait_until(lambda: all(c.status()["executed"] == 2 for c in api))

    cluster.kill(3)
    cluster.store(3).unlink()
    out = psystem(
        "restore", str(backup),
        "--to", str(cluster.store(3)),
        "--genesis", str(cluster.base / "genesis.json"),
        "--key", str(cluster.directory(3) / "identity.key"),
    )
    assert json.loads(out)["abstains_until_after_epoch"] == 0
    cluster.start(3, create=False)
    # It catches up on certificates.
    assert wait_until(lambda: api[3].status()["executed"] == 2)
    assert wait_until(lambda: same_state(api))

    # And signs nothing: with node 0 dead and 3 restored, 1 and 2 cannot reach a quorum alone.
    cluster.kill(0)
    third = money.transfer("bob", 1)
    assert api[1].submit(third)["accepted"]
    assert not api[1].wait_final(third.transfer, verifier(cluster), seconds=1.5)

    # A stale restore is the risk this rule closes: the restored file does not know this vote.
    cluster.start(0, create=False)
    assert wait_until(lambda: "node-0" in api[1].status()["peers"])
    api[1].submit(third)
    assert api[1].wait_final(third.transfer, verifier(cluster))


def test_committee_of_the_genesis_file_matches_what_the_command_printed(cluster):
    genesis = read_genesis(cluster.base / "genesis.json")
    assert genesis.committee.committee_id == cluster.genesis["committee_id"]
    assert genesis.file_hash == cluster.genesis["genesis_hash"]
    assert isinstance(genesis.committee, Committee)
    assert isinstance(genesis.state, State)
