"""Mission records through four real nodes, on real TLS, in separate processes."""

import json
import threading

import pytest

from core.event import Transfer
from core.signed_event import SignedTransfer
from crypto.identity import Identity
from network.deployment import read_genesis
from sdk.client import ApiError, ChainVerifier, Client, Wallet
from sdk.mission import MissionRecord, certified_record, record_asset, sign_record
from tests.deployment_helpers import Deployment, wait_until


@pytest.fixture
def running(tmp_path):
    deployment = Deployment(tmp_path)
    deployment.start_all()
    yield deployment
    deployment.stop_all()


def clients(deployment):
    return [Client(deployment.api_url(i)) for i in range(deployment.count)]


def verifier(deployment):
    genesis = read_genesis(deployment.base / "genesis.json")
    return ChainVerifier(genesis.committee, genesis.governance)


def records_of(client, verifier=None):
    found = {}
    after = 0
    while True:
        page = client.records(after=after)
        for item in page["records"]:
            certified = certified_record(item["certificate"], verifier)
            found[(certified.sender, certified.nonce)] = certified
        if page["next"] == after or not page["records"]:
            return found
        after = page["next"]


def new_wallet(tmp_path, name):
    identity = Identity.create()
    return Wallet(identity, tmp_path / f"{name}.sqlite", asset=record_asset(identity.identity_id))


def record(wallet, entity, version, body):
    return MissionRecord(entity, "observation", version, body, wallet.account, "2026-11-15T12:00:00Z")


def test_records_are_certified_and_every_node_returns_the_same_ones(running, tmp_path):
    check = verifier(running)
    rover = new_wallet(tmp_path, "rover")
    base = new_wallet(tmp_path, "base")
    signed = [
        sign_record(rover, record(rover, "site:SR12", 1, {"slope_deg": 4.2})),
        sign_record(rover, record(rover, "site:SR12", 2, {"slope_deg": 4.4})),
        sign_record(base, record(base, "power:base", 1, {"soc": 0.71})),
    ]
    api = clients(running)
    # Each event reaches one node only; the protocol carries it to the others.
    for index, event in enumerate(signed):
        api[index].submit(event)
    for event in signed:
        assert api[0].wait_final(event.transfer, check, seconds=60)

    expected = {(e.transfer.sender, e.transfer.nonce): e.transfer.event_id() for e in signed}
    assert wait_until(lambda: all(len(records_of(c)) == 3 for c in api), 30)
    for client in api:
        found = records_of(client, check)
        assert {key: value.event_id for key, value in found.items()} == expected
        assert found[(signed[0].transfer.sender, 0)].record.body == {"slope_deg": 4.2}
    status = [client.status() for client in api]
    assert len({s["state_root"] for s in status}) == 1
    assert not any(s["halted"] or s["conflicted"] for s in status)


def test_a_tampered_record_is_refused_by_the_api(running, tmp_path):
    rover = new_wallet(tmp_path, "rover")
    signed = sign_record(rover, record(rover, "site:SR12", 1, {"slope_deg": 4.2}))
    data = json.loads(signed.transfer.data)
    data["body"]["slope_deg"] = 1.0
    forged = SignedTransfer(
        Transfer(
            signed.transfer.sender,
            signed.transfer.receiver,
            1,
            0,
            (),
            json.dumps(data, sort_keys=True, separators=(",", ":")),
        ),
        signed.public_key,
        signed.signature,
    )
    with pytest.raises(ApiError) as refused:
        Client(running.api_url(0)).submit(forged)
    assert refused.value.status == 409


def test_two_versions_of_one_record_are_decided_once_for_every_node(running, tmp_path):
    check = verifier(running)
    rover = new_wallet(tmp_path, "rover")
    first = sign_record(rover, record(rover, "rover-1", 7, {"pos_rc": [100, 200]}), nonce=0)
    # The same key signs another version for nonce 0: a rover restored from a stale backup.
    second = SignedTransfer.create(
        rover.identity,
        Transfer(first.transfer.sender, first.transfer.receiver, 1, 0, (), record(rover, "rover-1", 7, {"pos_rc": [101, 205]}).to_data()),
    )
    api = clients(running)

    def send(client, event):
        try:
            client.submit(event)
        except ApiError:
            pass  # a node that saw the other version first refuses this one

    threads = [
        threading.Thread(target=send, args=(api[i], first if i < 2 else second)) for i in range(4)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    key = (first.transfer.sender, 0)
    assert wait_until(lambda: all(key in records_of(c) for c in api), 90)
    decided = {records_of(c, check)[key].event_id for c in api}
    assert len(decided) == 1
    assert decided <= {first.transfer.event_id(), second.transfer.event_id()}
    assert not any(c.status()["halted"] for c in api)


def test_a_node_that_was_down_recovers_the_records_it_missed(running, tmp_path):
    check = verifier(running)
    rover = new_wallet(tmp_path, "rover")
    running.kill(3)
    api = clients(running)
    signed = [sign_record(rover, record(rover, "rover-1", v, {"v": v})) for v in range(1, 6)]
    api[0].submit_many(signed)
    for event in signed:
        assert api[1].wait_final(event.transfer, check, seconds=60)

    running.start(3, create=False)
    recovered = Client(running.api_url(3))
    assert wait_until(lambda: len(records_of(recovered)) == 5, 60)
    assert {r.event_id for r in records_of(recovered, check).values()} == {e.transfer.event_id() for e in signed}
    assert recovered.status()["state_root"] == api[0].status()["state_root"]
