"""What a node asks votes for survives its death: a client that got a 202 need not send it again."""

import random
import sqlite3
import time

import pytest

from core.attestation import Vote
from core.event import Transfer
from core.state import State
from crypto.identity import Identity
from network import quorum as quorum_module
from network.message import encode_certificate, encode_vote, encode_vote_request
from network.node import Node
from network.quorum import QuorumDriver, QuorumReplica, SqliteVoteStore
from scripts import measure_network as measure
from sdk.client import Client
from tests.chaos import ChaosDeployment
from tests.deployment_helpers import wait_until
from tests.failure_evidence import ROOT
from tests.test_quorum_node import GENESIS, PAYER, signed
from tests.test_stuck_event import FIRST, UNTIL_A_STALL_HOLDS, Drivers, requested, transfer

BURST = 20


@pytest.fixture
def proxied(tmp_path):
    made = ChaosDeployment(tmp_path, random.Random(11))
    yield made
    made.close()


def test_a_node_killed_while_gathering_finishes_when_it_comes_back(proxied):
    # Every event is on its way, no answer can come back, and the client has its 202 for all of them.
    made = proxied
    made.start_all()
    clients = [Client(made.api_url(index)) for index in range(made.count)]
    measure.wait_connected(clients)
    sender = measure.Sender(Identity.load(made.sender_key))
    account = sender.identity.identity_id

    for peer in (1, 2, 3):
        for link in ((0, peer), (peer, 0)):
            made.links[link].stalled = True

    time.sleep(UNTIL_A_STALL_HOLDS)
    answer = clients[0].submit_many([sender.next() for _ in range(BURST)])
    assert answer["accepted"]
    made.kill(0)

    for link in made.links.values():
        link.cut()
        link.clear()

    # Whatever the others voted, the only node that could gather their votes is gone.
    time.sleep(1.0)
    assert all(measure.next_nonce_of(client, account) == 0 for client in clients[1:])
    made.start(0, create=False)
    measure.wait_for(clients, account, BURST, 20.0)
    assert len({client.status()["state_root"] for client in clients}) == 1


# --- With no network -------------------------------------------------------------------------------


def restart(drivers: Drivers) -> QuorumDriver:
    store = drivers.stores[0]
    store.close()
    store = SqliteVoteStore(
        drivers.directory / "driver-0.sqlite",
        drivers.four.committee,
        drivers.four.members[0].public_key,
    )
    drivers.stores[0] = store
    driver = QuorumDriver(
        QuorumReplica(drivers.four.members[0], GENESIS, store, lambda _: True),
        clock=drivers.clock,
    )
    drivers.drivers[0] = driver
    return driver


def vote_of(drivers: Drivers, index: int, event: Transfer) -> dict:
    return encode_vote(event, Vote.create(drivers.four.committee, drivers.four.members[index], event))


@pytest.fixture
def drivers(tmp_path):
    made = Drivers(tmp_path)
    made.directory = tmp_path
    yield made
    made.close()


def test_an_event_is_asked_for_at_once_as_it_was_signed_after_a_restart(drivers):
    event = transfer(0)
    drivers.first.submit(event)
    driver = restart(drivers)
    assert driver.gathering_count == 1
    assert drivers.at(0) == [encode_vote_request(event)]


def test_the_votes_of_before_are_gone_and_its_own_vote_comes_back(drivers):
    event = transfer(0)
    drivers.first.submit(event)
    drivers.first.handle_message(vote_of(drivers, 1, event.transfer))
    restart(drivers)
    voted = drivers.first.replica.votes()
    drivers.at(0)
    # Its own, signed again, and no second row: one peer is not enough, two are.
    assert drivers.first.replica.votes() == voted
    assert drivers.first.handle_message(vote_of(drivers, 1, event.transfer)).broadcasts == ()
    output = drivers.first.handle_message(vote_of(drivers, 2, event.transfer))
    assert output.broadcasts
    assert drivers.first.replica.state.nonce(PAYER) == 1


def test_an_event_that_ran_is_not_asked_for_after_a_restart(drivers):
    event = transfer(0)
    drivers.first.submit(event)

    for index in (1, 2):
        drivers.first.handle_message(vote_of(drivers, index, event.transfer))

    assert restart(drivers).gathering_count == 0
    assert drivers.at(FIRST) == []


def test_a_certificate_that_came_from_elsewhere_ends_it_on_disk_too(drivers):
    event = transfer(0)
    drivers.first.submit(event)
    drivers.first.handle_message(encode_certificate(drivers.four.certificate(event.transfer)))
    assert restart(drivers).gathering_count == 0


def test_a_certificate_waiting_for_an_earlier_nonce_keeps_its_event_on_disk(drivers):
    # That certificate is in memory and a restart loses it, so the event must not go.
    event = transfer(1)
    drivers.first.submit(event)

    for index in (1, 2):
        drivers.first.handle_message(vote_of(drivers, index, event.transfer))

    assert drivers.first.replica.state.nonce(PAYER) == 0
    assert drivers.at(FIRST) == []
    restart(drivers)
    assert requested(drivers.at(FIRST)) == [1]


def test_a_certificate_from_elsewhere_waiting_for_an_earlier_nonce_keeps_its_event_too(drivers):
    event = transfer(1)
    drivers.first.submit(event)
    drivers.first.handle_message(encode_certificate(drivers.four.certificate(event.transfer)))
    assert drivers.first.replica.state.nonce(PAYER) == 0
    assert drivers.at(FIRST) == []
    restart(drivers)
    assert requested(drivers.at(FIRST)) == [1]


def test_another_version_certified_ends_it_on_disk_too(drivers):
    event = transfer(1)
    drivers.first.submit(event)
    other = Transfer(PAYER, "carol", 1, 1)
    drivers.first.handle_message(encode_certificate(drivers.four.certificate(other)))
    assert drivers.at(FIRST) == []
    assert restart(drivers).gathering_count == 0


def test_votes_split_stay_asked_for_after_a_restart(drivers):
    # The limit written in the plan: nobody can tell this event will never get a quorum.
    event = transfer(0)
    drivers.first.submit(event)
    restart(drivers)
    assert requested(drivers.at(0)) == [0]
    assert requested(drivers.at(2 * FIRST)) == [0]


def test_a_vote_for_the_event_of_another_node_is_not_this_node_gathering(drivers):
    drivers.first.handle_message(encode_vote_request(transfer(0)))
    assert restart(drivers).gathering_count == 0


def test_an_event_voted_for_first_and_then_taken_is_gathering(drivers):
    event = transfer(0)
    drivers.first.handle_message(encode_vote_request(event))
    drivers.first.submit(event)
    assert restart(drivers).gathering_count == 1


def test_nothing_is_on_disk_for_a_group_that_failed(drivers):
    store = drivers.stores[0]
    event = transfer(0)

    with pytest.raises(RuntimeError):
        with store.group():
            assert store.record_vote(event.transfer, event, gathering=True)
            raise RuntimeError

    assert store.gathering() == []
    assert store.votes() == []


def test_a_store_restored_from_a_backup_asks_and_signs_nothing(drivers):
    event = transfer(0)
    drivers.first.submit(event)
    drivers.stores[0].mark_restored()
    restart(drivers)
    assert requested(drivers.at(0)) == [0]
    assert drivers.first._aggregating[event.transfer.canonical()][1] == {}

    # With no vote of its own it takes three, and that is still a certificate.
    for index in (1, 2):
        assert drivers.first.handle_message(vote_of(drivers, index, event.transfer)).broadcasts == ()

    assert drivers.first.handle_message(vote_of(drivers, 3, event.transfer)).broadcasts


def test_no_more_comes_back_than_a_node_may_gather(drivers, monkeypatch):
    for nonce in range(3):
        drivers.first.submit(transfer(nonce))

    monkeypatch.setattr(quorum_module, "MAX_AGGREGATING_EVENTS", 2)
    assert restart(drivers).gathering_count == 2


def test_nothing_comes_back_after_a_halt(drivers):
    drivers.first.submit(transfer(5))

    for version in (Transfer(PAYER, "bob", 1, 1), Transfer(PAYER, "carol", 1, 1)):
        drivers.first.handle_message(encode_certificate(drivers.four.certificate(version)))

    assert drivers.first.halted
    assert drivers.stores[0].gathering()
    assert restart(drivers).gathering_count == 0


def test_a_file_of_schema_5_opens_with_nothing_gathering(tmp_path):
    made = Drivers(tmp_path)
    made.directory = tmp_path
    event = Transfer(PAYER, "bob", 1, 0)
    assert made.stores[0].record_vote(event, signed(event))
    made.close()
    connection = sqlite3.connect(tmp_path / "driver-0.sqlite")
    connection.execute("DROP TABLE gathering")
    connection.execute("UPDATE meta SET value = '5' WHERE key = 'schema_version'")
    connection.commit()
    connection.close()
    store = SqliteVoteStore(
        tmp_path / "driver-0.sqlite",
        made.four.committee,
        made.four.members[0].public_key,
    )
    assert store.gathering() == []
    assert store.votes() == [event]
    version = store._connection.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    assert version == ("6",)
    store.close()
