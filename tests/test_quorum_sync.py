"""Synchronization of certificates (network/quorum.py and network/message.py).

No network here: the messages of one driver are given to another, after a pass through JSON.
The real network is in tests/test_quorum_differential_network.py.
"""

import json

import pytest

from core.attestation import Committee, QuorumCertificate, Vote
from core.derive import StateDeriver
from core.event import Transfer
from core.state import State
from crypto.identity import Identity
from network import quorum as quorum_module
from network.message import (
    decode_certificate_sync,
    decode_certificate_sync_request,
    encode_certificate,
    encode_certificate_sync,
    encode_certificate_sync_request,
)
from network.quorum import QuorumDriver, QuorumReplica, SqliteVoteStore

MEMBERS = [Identity.create() for _ in range(4)]
GENESIS = State({"alice": 100, "bob": 100})
COMMITTEE = Committee.create([m.public_key for m in MEMBERS], 1, GENESIS)
MEMBERS.sort(key=lambda member: member.public_key)


def wire(message: dict) -> dict:
    return json.loads(json.dumps(message))


def certificate(event: Transfer, signers=(0, 1, 2)) -> QuorumCertificate:
    return QuorumCertificate(
        event,
        tuple(Vote.create(COMMITTEE, MEMBERS[index], event) for index in signers),
    )


def alice(nonce: int, receiver: str = "bob", parents=()) -> Transfer:
    return Transfer("alice", receiver, 1, nonce, tuple(parents))


def bob(nonce: int, receiver: str = "carol", parents=()) -> Transfer:
    return Transfer("bob", receiver, 1, nonce, tuple(parents))


@pytest.fixture
def make_driver(tmp_path):
    made = []

    def make(index: int = 0, genesis: State = GENESIS, committee=COMMITTEE):
        store = SqliteVoteStore(
            tmp_path / f"{len(made)}.sqlite",
            committee,
            MEMBERS[index].public_key,
            create=True,
        )
        made.append(store)
        replica = QuorumReplica(MEMBERS[index], genesis, store, lambda _event: True)
        return QuorumDriver(replica)

    yield make

    for store in made:
        store.close()


def deliver(driver: QuorumDriver, *events: Transfer) -> None:
    for event in events:
        driver.handle_message(wire(encode_certificate(certificate(event))))


def exchange(behind: QuorumDriver, ahead: QuorumDriver, limit: int = 100) -> int:
    """Run the conversation to its end and return how many answers it took."""
    answers = 0
    request = behind.sync_request()

    while request is not None:
        assert answers < limit, "the exchange does not end"
        replies = ahead.handle_message(wire(request)).replies

        if not replies:
            break

        answers += 1
        following = behind.handle_message(wire(replies[0])).replies
        request = following[0] if following else None

    return answers


# --- The message ------------------------------------------------------------------------


def test_request_round_trip():
    frontier = {"bob": 3, "alice": 0}
    message = wire(encode_certificate_sync_request(frontier))
    assert message["frontier"] == [["alice", 0], ["bob", 3]]
    assert decode_certificate_sync_request(message) == frontier


@pytest.mark.parametrize(
    "frontier",
    [
        "nope",
        5,
        None,
        {"alice": 1},
        [5],
        [None],
        ["ab"],
        [["alice"]],
        [["alice", 1, 2]],
        ["alice"],
        [[1, 1]],
        [["", 1]],
        [["alice", -1]],
        [["alice", True]],
        [["alice", 2**256]],
        [["alice", "1"]],
        [["bob", 1], ["alice", 1]],
        [["alice", 1], ["alice", 2]],
    ],
)
def test_malformed_request_is_a_value_error(frontier):
    with pytest.raises(ValueError):
        decode_certificate_sync_request(
            {"type": "CERTIFICATE_SYNC_REQUEST", "frontier": frontier}
        )


@pytest.mark.parametrize(
    "message",
    [
        {"type": "CERTIFICATE_SYNC_REQUEST"},
        {"type": "CERTIFICATE_SYNC", "frontier": []},
        {"type": "CERTIFICATE_SYNC_REQUEST", "frontier": [], "extra": 1},
    ],
)
def test_request_of_the_wrong_shape_is_a_value_error(message):
    with pytest.raises(ValueError):
        decode_certificate_sync_request(message)


# --- Asking -----------------------------------------------------------------------------


def test_new_node_asks_with_an_empty_frontier(make_driver):
    assert decode_certificate_sync_request(make_driver().sync_request()) == {}


def test_frontier_is_the_next_nonce_of_each_sender(make_driver):
    driver = make_driver()
    deliver(driver, alice(0), alice(1), bob(0))
    assert decode_certificate_sync_request(driver.sync_request()) == {"alice": 2, "bob": 1}


def test_frontier_counts_what_waits_in_the_buffer(make_driver):
    driver = make_driver()
    parent = bob(0)
    waiting = alice(0, parents=(parent.event_id(),))
    deliver(driver, waiting)
    assert driver.replica.executed == []
    assert decode_certificate_sync_request(driver.sync_request()) == {"alice": 1}


def test_frontier_does_not_jump_over_a_hole(make_driver):
    driver = make_driver()
    deliver(driver, alice(1))
    assert decode_certificate_sync_request(driver.sync_request()) == {"alice": 0}


def test_frontier_keeps_within_its_limit(make_driver, monkeypatch):
    monkeypatch.setattr(quorum_module, "SYNC_MAX_FRONTIER_SENDERS", 1)
    driver = make_driver()
    deliver(driver, alice(0), bob(0))
    assert decode_certificate_sync_request(driver.sync_request()) == {"alice": 1}


# --- Answering --------------------------------------------------------------------------


def test_answer_holds_only_what_the_frontier_lacks(make_driver):
    driver = make_driver()
    deliver(driver, alice(0), alice(1), bob(0))
    request = encode_certificate_sync_request({"alice": 1, "bob": 1})
    reply = driver.handle_message(wire(request)).replies[0]
    assert [c.event for c in decode_certificate_sync(wire(reply))] == [alice(1)]


def test_nothing_to_send_is_no_answer(make_driver):
    driver = make_driver()
    deliver(driver, alice(0))
    request = encode_certificate_sync_request({"alice": 1})
    assert driver.handle_message(wire(request)).replies == ()


def test_answer_respects_a_nonce_that_does_not_start_at_zero(make_driver):
    genesis = State({"alice": 10}, {"alice": 5})
    committee = Committee.create([m.public_key for m in MEMBERS], 1, genesis)
    driver = make_driver(committee=committee, genesis=genesis)
    events = [alice(5), alice(6)]

    for event in events:
        driver.handle_message(
            wire(
                encode_certificate(
                    QuorumCertificate(
                        event,
                        tuple(
                            Vote.create(committee, MEMBERS[index], event)
                            for index in (0, 1, 2)
                        ),
                    )
                )
            )
        )

    assert driver.replica.executed == events
    request = encode_certificate_sync_request({"alice": 6})
    reply = driver.handle_message(wire(request)).replies[0]
    assert [c.event for c in decode_certificate_sync(wire(reply))] == [alice(6)]


def test_answer_respects_the_limit_on_a_batch(make_driver, monkeypatch):
    monkeypatch.setattr(quorum_module, "SYNC_BATCH_BYTES", 1)
    driver = make_driver()
    deliver(driver, alice(0), alice(1))
    reply = driver.handle_message(
        wire(encode_certificate_sync_request({}))
    ).replies[0]
    # One always goes, or a small limit would stop everything.
    assert [c.event for c in decode_certificate_sync(wire(reply))] == [alice(0)]


def test_a_halted_node_still_answers_and_stops_asking(make_driver):
    driver = make_driver()
    deliver(driver, alice(0), alice(1, "carol"))
    deliver(driver, alice(1, "dave"))
    assert driver.halted
    assert driver.sync_request() is None
    assert driver.handle_message(wire(encode_certificate_sync_request({}))).replies


# --- Catching up ------------------------------------------------------------------------


def test_a_node_left_behind_catches_up(make_driver):
    ahead, behind = make_driver(0), make_driver(1)
    events = [alice(0), bob(0), alice(1), bob(1)]
    deliver(ahead, *events)

    assert exchange(behind, ahead) == 1
    assert behind.replica.state.root() == ahead.replica.state.root()
    assert behind.replica.state.root() == StateDeriver.apply_events(
        GENESIS.copy(), behind.replica.executed
    ).root()


def test_small_batches_reach_the_end(make_driver, monkeypatch):
    monkeypatch.setattr(quorum_module, "SYNC_BATCH_BYTES", 1)
    ahead, behind = make_driver(0), make_driver(1)
    deliver(ahead, alice(0), alice(1), alice(2), bob(0))

    assert exchange(behind, ahead) == 4
    assert behind.replica.state.root() == ahead.replica.state.root()


def test_batches_that_cannot_run_yet_do_not_stop_the_exchange(make_driver, monkeypatch):
    # Alice sorts first and her event waits for Bob's. Without counting the buffer the same
    # answer would come back, nothing would be new, and the exchange would end there.
    monkeypatch.setattr(quorum_module, "SYNC_BATCH_BYTES", 1)
    ahead, behind = make_driver(0), make_driver(1)
    parent = bob(0)
    child = alice(0, parents=(parent.event_id(),))
    deliver(ahead, parent, child)
    assert ahead.replica.executed == [parent, child]

    assert exchange(behind, ahead) == 2
    assert behind.replica.state.root() == ahead.replica.state.root()


def test_the_exchange_ends_when_there_is_nothing_new(make_driver):
    ahead, behind = make_driver(0), make_driver(1)
    deliver(ahead, alice(0))
    deliver(behind, alice(0))
    assert exchange(behind, ahead) == 0


def test_a_batch_of_known_certificates_asks_nothing_more(make_driver):
    driver = make_driver()
    deliver(driver, alice(0))
    batch = encode_certificate_sync([certificate(alice(0))])
    assert driver.handle_message(wire(batch)).replies == ()


def test_certificates_that_can_never_run_do_not_loop_the_exchange(make_driver):
    # The peer sends again what stays in the buffer. Nothing new, so nothing more.
    driver = make_driver()
    stuck = Transfer("alice", "bob", 1000, 0)
    batch = encode_certificate_sync([certificate(stuck)])

    assert driver.handle_message(wire(batch)).replies != ()
    assert driver.handle_message(wire(batch)).replies == ()
    assert driver.replica.executed == []


# --- A peer that lies -------------------------------------------------------------------


def test_conflict_in_a_batch_halts_and_keeps_the_proof(make_driver):
    driver = make_driver()
    deliver(driver, alice(0, "carol"))
    batch = encode_certificate_sync([certificate(alice(0, "dave"))])

    assert driver.handle_message(wire(batch)).replies == ()
    assert driver.halted
    assert driver.replica.halt_proof() is not None


def test_certificates_after_a_halt_in_the_same_batch_do_not_run(make_driver):
    driver = make_driver()
    deliver(driver, alice(0, "carol"))
    batch = encode_certificate_sync(
        [certificate(alice(0, "dave")), certificate(bob(0))]
    )
    driver.handle_message(wire(batch))
    assert driver.replica.executed == [alice(0, "carol")]
    # Not even kept for later: a halt empties the buffer, and nothing fills it again.
    assert driver._buffer == {}


def forged(event: Transfer) -> QuorumCertificate:
    # Signed by member 3 on behalf of three members.
    votes = tuple(
        Vote(index, Vote.create(COMMITTEE, MEMBERS[3], event).signature)
        for index in (0, 1, 2)
    )
    return QuorumCertificate(event, votes)


def test_forged_certificate_in_a_batch_changes_nothing(make_driver):
    driver = make_driver()
    batch = encode_certificate_sync([forged(alice(0))])

    assert driver.handle_message(wire(batch)).replies == ()
    assert driver.replica.executed == []
    assert not driver.halted
    assert decode_certificate_sync_request(driver.sync_request()) == {}


def test_forged_conflict_in_a_batch_does_not_halt(make_driver):
    driver = make_driver()
    deliver(driver, alice(0, "carol"))
    driver.handle_message(wire(encode_certificate_sync([forged(alice(0, "dave"))])))
    assert not driver.halted


def test_what_came_before_a_forged_certificate_stays(make_driver):
    driver = make_driver()
    batch = encode_certificate_sync([certificate(alice(0)), forged(alice(1))])
    driver.handle_message(wire(batch))
    assert driver.replica.executed == [alice(0)]


def _count_verifications(monkeypatch) -> list:
    calls = []
    real = QuorumCertificate.verify

    def counting(self, committee):
        calls.append(self.event.nonce)
        return real(self, committee)

    monkeypatch.setattr(QuorumCertificate, "verify", counting)
    return calls


def test_a_frame_of_bad_certificates_stops_at_the_first(make_driver, monkeypatch):
    driver = make_driver()
    batch = encode_certificate_sync([forged(alice(n)) for n in range(50)])
    calls = _count_verifications(monkeypatch)
    driver.handle_message(wire(batch))
    assert len(calls) == 1


def test_sending_the_log_again_checks_no_signature(make_driver, monkeypatch):
    driver = make_driver()
    events = [alice(n) for n in range(5)]
    deliver(driver, *events)
    batch = encode_certificate_sync([certificate(event) for event in events])
    calls = _count_verifications(monkeypatch)
    driver.handle_message(wire(batch))
    assert calls == []


@pytest.mark.parametrize(
    "message",
    [
        {"type": "CERTIFICATE_SYNC", "certificates": "nope"},
        {"type": "CERTIFICATE_SYNC", "certificates": [{"type": "CERTIFICATE"}]},
        {"type": "CERTIFICATE_SYNC_REQUEST", "frontier": [["alice", -1]]},
    ],
)
def test_malformed_message_is_a_value_error_for_the_caller(make_driver, message):
    with pytest.raises(ValueError):
        make_driver().handle_message(message)
