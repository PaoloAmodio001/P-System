"""An attacker that exhausts memory or CPU today, and does not after these defenses.

archive/docs/proposte/passo-4.md has what each attack cost before them. Each limit here must leave the result
of an honest sender alone: a test below delivers in every order, with a buffer that holds almost nothing.
"""

import json
import random
import socket
import threading
import time

import pytest

from core.attestation import Committee, QuorumCertificate, Vote
from core.event import Transfer
from core.signed_event import SignedTransfer
from core.state import State
from crypto.identity import Identity
from network.message import (
    encode_certificate,
    encode_certificate_sync,
    encode_certificate_sync_request,
    encode_vote_request,
)
from network.node import REPLY_BYTES_PER_TOKEN, Node
from network.node_tls_identity import get_node_tls_config
from network.peer import Peer
from network.peer_connection import Pacer, PeerConnection
from network.quorum import (
    BAD_SIGNATURE_COST,
    DriverOutput,
    QuorumConfig,
    QuorumDriver,
    QuorumReplica,
    SqliteVoteStore,
)
from network.secure_transport import SecureTransport

SENDER = Identity.create()
ALICE = SENDER.identity_id
GENESIS = State({ALICE: 10**6})
MEMBERS = sorted((Identity.create() for _ in range(4)), key=lambda m: m.public_key)
COMMITTEE = Committee.create([m.public_key for m in MEMBERS], 1, GENESIS)


def wire(message: dict) -> dict:
    return json.loads(json.dumps(message))


def transfer(nonce: int, sender: str = ALICE, receiver: str = "bob", amount: int = 1) -> Transfer:
    return Transfer(sender, receiver, amount, nonce)


def certificate(event: Transfer) -> QuorumCertificate:
    return QuorumCertificate(
        event,
        tuple(Vote.create(COMMITTEE, member, event) for member in MEMBERS[:3]),
    )


def driver_at(path, index=0, **settings) -> QuorumDriver:
    store = SqliteVoteStore(path, COMMITTEE, MEMBERS[index].public_key, create=True)
    replica = QuorumReplica(MEMBERS[index], GENESIS, store, lambda _event: True)
    return QuorumDriver(replica, **settings)


def wait_until(condition, seconds: float = 10.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return condition()


# --- Silent connections ---------------------------------------------------------------------------


def quorum_nodes(tmp_path, *names):
    made = [
        Node(
            name,
            GENESIS,
            quorum=QuorumConfig(
                COMMITTEE,
                MEMBERS[index],
                tmp_path / f"{name}.sqlite",
                create=True,
                sync_interval=None,
            ),
        )
        for index, name in enumerate(names)
    ]

    for node in made:
        node.start()

    return made


def test_silent_connections_do_not_keep_an_honest_peer_out(tmp_path):
    # With no certificate. Before: 70 of these, and every honest peer was refused.
    victim, honest = quorum_nodes(tmp_path, "mute-victim", "mute-honest")
    silent = []

    try:
        for _ in range(100):
            silent.append(socket.create_connection(victim.address()))

        host, port = victim.address()
        assert wait_until(lambda: len(victim._server_controller._pending) > 0)
        assert honest.connect_peer(Peer(node_id=victim.node_id, host=host, port=port))
    finally:
        for connection in silent:
            connection.close()
        honest.stop()
        victim.stop()


def test_silent_connections_hold_no_more_than_their_places(tmp_path):
    [victim] = quorum_nodes(tmp_path, "mute-only")
    controller = victim._server_controller
    before = threading.active_count()
    silent = []

    try:
        for _ in range(200):
            silent.append(socket.create_connection(victim.address()))

        time.sleep(0.3)
        assert len(controller._pending) <= controller.MAX_PENDING_PER_ADDRESS
        assert threading.active_count() - before <= 2 * controller.MAX_PENDING_PER_ADDRESS
    finally:
        for connection in silent:
            connection.close()
        victim.stop()


def from_address(node, address, count):
    made = []
    for _ in range(count):
        connection = socket.socket()
        connection.bind((address, 0))
        connection.connect(node.address())
        made.append(connection)
    return made


def is_open(connection) -> bool:
    connection.setblocking(False)
    try:
        return connection.recv(1) != b""
    except BlockingIOError:
        return True
    except OSError:
        return False
    finally:
        connection.setblocking(True)


def test_one_address_does_not_push_out_another(tmp_path):
    [victim] = quorum_nodes(tmp_path, "mute-address")
    controller = victim._server_controller
    quiet = from_address(victim, "127.0.0.2", 4)
    assert wait_until(lambda: len(controller._pending) == 4)
    loud = from_address(victim, "127.0.0.3", 100)

    try:
        assert wait_until(
            lambda: len(controller._pending) == 4 + controller.MAX_PENDING_PER_ADDRESS
        )
        time.sleep(0.2)
        assert all(is_open(connection) for connection in quiet)
        assert sum(not is_open(connection) for connection in loud) >= 80
    finally:
        for connection in (*quiet, *loud):
            connection.close()
        victim.stop()


def test_with_many_addresses_there_is_still_a_limit_for_all(tmp_path):
    [victim] = quorum_nodes(tmp_path, "mute-many")
    controller = victim._server_controller
    controller.MAX_PENDING_HANDSHAKES = 8
    made = []

    try:
        for last in range(2, 12):
            made.extend(from_address(victim, f"127.0.0.{last}", 2))

        time.sleep(0.3)
        assert len(controller._pending) <= 8
    finally:
        for connection in made:
            connection.close()
        victim.stop()


# --- Paying by cost -------------------------------------------------------------------------------


def bad_request() -> dict:
    signed = SignedTransfer.create(SENDER, transfer(0))
    return encode_vote_request(SignedTransfer(signed.transfer, signed.public_key, b"\0" * 64))


def test_each_kind_of_bad_signature_costs_the_peer(tmp_path):
    driver = driver_at(tmp_path / "a.sqlite")
    event = transfer(0)
    forged = QuorumCertificate(event, tuple(Vote(index, b"\1" * 64) for index in range(3)))
    assert driver.handle_message(wire(bad_request())).cost == BAD_SIGNATURE_COST
    assert driver.handle_message(wire(encode_certificate(forged))).cost == BAD_SIGNATURE_COST
    assert driver.handle_message(wire(encode_certificate_sync([forged]))).cost == BAD_SIGNATURE_COST


def test_a_good_message_costs_nothing_extra(tmp_path):
    driver = driver_at(tmp_path / "a.sqlite")
    signed = SignedTransfer.create(SENDER, transfer(0))
    assert driver.handle_message(wire(encode_vote_request(signed))).cost == 0
    assert driver.handle_message(wire(encode_certificate(certificate(transfer(0))))).cost == 0


def test_a_cost_is_not_carried_to_the_next_message(tmp_path):
    driver = driver_at(tmp_path / "a.sqlite")
    assert driver.handle_message(wire(bad_request())).cost
    assert driver.handle_message(wire(encode_certificate_sync_request({}))).cost == 0


def test_a_request_that_would_be_refused_anyway_costs_no_signature(tmp_path, monkeypatch):
    driver = driver_at(tmp_path / "a.sqlite", max_nonce_ahead=4)
    calls = []
    monkeypatch.setattr(
        SignedTransfer,
        "verify",
        lambda self: calls.append(self) or True,
    )
    signed = SignedTransfer.create(SENDER, transfer(1000))
    assert driver.handle_message(wire(encode_vote_request(signed))).replies == ()
    driver.submit(signed)
    assert calls == []


def test_a_group_adds_up_what_its_messages_cost(tmp_path):
    from network.quorum import QuorumRuntime

    run = QuorumRuntime(QuorumConfig(COMMITTEE, MEMBERS[0], tmp_path / "g.sqlite", create=True), GENESIS)
    output, error = run.handle_group([wire(bad_request()), wire(bad_request())])
    assert error is None
    assert output.cost == 2 * BAD_SIGNATURE_COST
    run.close()


def test_a_pacer_waits_in_short_steps_and_keeps_the_debt():
    waits = []
    now = [0.0]
    pacer = Pacer(100.0, 0.0, clock=lambda: now[0], sleep=waits.append)
    pacer.take(1000)
    assert waits == [Pacer.MAX_WAIT]
    pacer.take(1)
    assert waits[-1] == Pacer.MAX_WAIT


def test_a_pacer_pays_a_debt_back_over_time():
    waits = []
    now = [0.0]
    pacer = Pacer(100.0, 0.0, clock=lambda: now[0], sleep=waits.append)
    pacer.take(50)
    assert waits == [0.5]
    now[0] += 1.0
    pacer.take(1)
    # Paid: only the new token is left to wait for.
    assert waits[1] == pytest.approx(0.01)


class Recording:
    def __init__(self):
        self.charged = []
        self.sent = []

    def charge(self, tokens):
        self.charged.append(tokens)

    def enqueue(self, message):
        self.sent.append(message)
        return 10 * REPLY_BYTES_PER_TOKEN

    def close(self):
        pass


def test_the_cost_and_the_answer_go_to_the_connection_that_asked():
    connection = Recording()
    node = Node.__new__(Node)
    output = DriverOutput(({"type": "X"},), (), 7)
    node._peer_connections_lock = threading.Lock()
    node.peer_connections = {}
    node._send_quorum_output(output, connection)
    assert connection.charged == [7, 10]


def test_no_connection_no_cost():
    node = Node.__new__(Node)
    node._peer_connections_lock = threading.Lock()
    node.peer_connections = {}
    node._send_quorum_output(DriverOutput((), (), 7), None)


def tls_flood(node, tmp_path, message, count, name):
    """A peer with a certificate of the authority, and with no rule."""
    raw = socket.create_connection(node.address())
    context = SecureTransport.create_client_context(get_node_tls_config(name))
    connection = SecureTransport.wrap_client(raw, context, node.node_id)
    from network.handshake import Handshake

    SecureTransport.send(connection, Handshake(name, "127.0.0.1", 1).encode())
    SecureTransport.receive(connection)
    peer = PeerConnection.adopt(name, connection, Handshake(node.node_id, "127.0.0.1", 1))
    stop = threading.Event()

    def flood():
        try:
            for _ in range(count):
                if stop.is_set():
                    return
                peer.send(message)
        except OSError:
            pass

    thread = threading.Thread(target=flood, daemon=True)
    thread.start()
    return peer, stop


def test_a_flood_of_bad_signatures_gets_few_checks(tmp_path, monkeypatch):
    # Before: 5000 checks per second for each connection, more than half of a core.
    [victim] = quorum_nodes(tmp_path, "flood-signatures")
    calls = []
    real = SignedTransfer.verify
    monkeypatch.setattr(
        SignedTransfer,
        "verify",
        lambda self: calls.append(1) or real(self),
    )
    peer, stop = tls_flood(victim, tmp_path, bad_request(), 100_000, "flood-peer")

    try:
        assert wait_until(lambda: len(calls) > 0)
        time.sleep(2.0)
        # The burst of 10000 tokens and 50 per second.
        assert len(calls) < 100 + 50 * 4
    finally:
        stop.set()
        peer.close()
        victim.stop()


def test_a_flood_of_requests_for_a_long_answer_is_slowed_to_what_it_costs(tmp_path, monkeypatch):
    # Before: 28 ms under the lock of the node for each request, and 5000 requests per second.
    [victim] = quorum_nodes(tmp_path, "flood-sync")
    driver = victim._quorum.driver

    for nonce in range(300):
        event = transfer(nonce)
        assert driver.replica.handle_certificate(certificate(event))

    answers = []
    real = driver._handle_sync_request
    monkeypatch.setattr(
        driver,
        "_handle_sync_request",
        lambda *args: answers.append(1) or real(*args),
    )
    monkeypatch.setattr(PeerConnection, "MAX_MESSAGES_PER_SECOND", 5000.0)
    peer, stop = tls_flood(victim, tmp_path, encode_certificate_sync_request({}), 100_000, "flood-sync-peer")

    try:
        assert wait_until(lambda: len(answers) > 0)
        time.sleep(2.0)
        # About 200 KiB for each answer, at 5 MiB per second, after the burst of 10000 tokens.
        assert len(answers) < 300
    finally:
        stop.set()
        peer.close()
        victim.stop()


def test_a_peer_that_floods_does_not_slow_another(tmp_path):
    # The wait is on the reader of that peer: another event goes through, as fast as ever.
    victim, other = quorum_nodes(tmp_path, "flood-a", "flood-b")
    host, port = victim.address()
    assert other.connect_peer(Peer(node_id=victim.node_id, host=host, port=port))
    peer, stop = tls_flood(victim, tmp_path, bad_request(), 100_000, "flood-c")

    try:
        time.sleep(0.5)
        signed = SignedTransfer.create(SENDER, transfer(0))
        started = time.monotonic()
        assert other.submit(signed)
        assert wait_until(lambda: victim._quorum.driver.replica.votes() != [], seconds=2.0)
        assert time.monotonic() - started < 2.0
    finally:
        stop.set()
        peer.close()
        other.stop()
        victim.stop()


# --- The buffer -------------------------------------------------------------------------------------


def test_a_certificate_too_far_ahead_is_left_out(tmp_path):
    driver = driver_at(tmp_path / "a.sqlite", max_nonce_ahead=4)
    driver.handle_message(wire(encode_certificate(certificate(transfer(5)))))
    assert driver._buffer == {}
    assert driver.certificates_left_out == 1
    driver.handle_message(wire(encode_certificate(certificate(transfer(4)))))
    assert len(driver._buffer) == 1


def test_the_buffer_has_a_limit_for_all(tmp_path):
    # Before: no limit, about 0.85 KB for each certificate, for good.
    driver = driver_at(tmp_path / "a.sqlite")
    driver.max_buffered = 3
    for nonce in range(1, 6):
        driver._accept(certificate(transfer(nonce)))
    assert len(driver._buffer) == 3
    assert driver.certificates_left_out == 2


def test_the_next_nonce_of_a_sender_enters_with_no_room(tmp_path):
    # It may need funds that are on their way, and it is the one that can run.
    driver = driver_at(tmp_path / "a.sqlite")
    driver.max_buffered = 0
    poor = "poor"
    driver._accept(certificate(transfer(0, sender=poor)))
    assert len(driver._buffer) == 1
    driver._accept(certificate(transfer(1)))
    assert len(driver._buffer) == 1
    driver._accept(certificate(transfer(0)))
    assert driver.replica.state.nonce(ALICE) == 1


def test_one_left_out_comes_back_when_there_is_room(tmp_path):
    driver = driver_at(tmp_path / "a.sqlite")
    driver.max_buffered = 0
    driver._accept(certificate(transfer(1)))
    assert driver.replica.state.nonce(ALICE) == 0
    driver._accept(certificate(transfer(0)))
    driver._accept(certificate(transfer(1)))
    assert driver.replica.state.nonce(ALICE) == 2


def test_a_conflict_is_still_seen_after_one_was_left_out(tmp_path):
    driver = driver_at(tmp_path / "a.sqlite")
    driver.max_buffered = 0
    driver._accept(certificate(transfer(1, receiver="x")))
    driver._accept(certificate(transfer(0)))
    driver._accept(certificate(transfer(1, receiver="x")))
    driver._accept(certificate(transfer(1, receiver="y")))
    assert driver.halted


def test_a_halt_empties_what_waits(tmp_path):
    driver = driver_at(tmp_path / "a.sqlite")
    driver._accept(certificate(transfer(3, receiver="x")))
    driver._accept(certificate(transfer(3, receiver="y")))
    assert driver.halted
    assert driver._buffer == {}
    assert driver._waiting == {}


def test_what_waits_further_on_costs_nothing_for_a_new_certificate(tmp_path, monkeypatch):
    # Before: each new certificate tried all of them, with a read of the disk for each.
    driver = driver_at(tmp_path / "a.sqlite")
    for nonce in range(1, 2001):
        driver._accept(certificate(transfer(nonce, sender="stuck")))
    calls = []
    real = driver.replica.handle_certificate
    monkeypatch.setattr(
        driver.replica,
        "handle_certificate",
        lambda item: calls.append(item) or real(item),
    )
    driver._accept(certificate(transfer(0)))
    assert len(calls) == 1
    assert driver.replica.state.nonce(ALICE) == 1


def test_waiting_certificates_run_in_order_when_the_first_arrives(tmp_path):
    driver = driver_at(tmp_path / "a.sqlite")
    for nonce in (3, 2, 1):
        driver._accept(certificate(transfer(nonce)))
    assert driver.replica.state.nonce(ALICE) == 0
    driver._accept(certificate(transfer(0)))
    assert driver.replica.state.nonce(ALICE) == 4
    assert driver._buffer == {}
    assert driver._waiting == {}


def test_funds_that_arrive_free_another_sender_that_waits(tmp_path):
    driver = driver_at(tmp_path / "a.sqlite")
    driver._accept(certificate(transfer(0, sender="bob", receiver="carol", amount=5)))
    assert len(driver._buffer) == 1
    driver._accept(certificate(transfer(0, amount=5)))
    assert driver._buffer == {}
    assert driver.replica.state.balance("carol") == 5


def test_a_batch_with_nothing_kept_does_not_ask_again(tmp_path):
    # Otherwise two nodes would go on asking each other for what one has no room for.
    driver = driver_at(tmp_path / "a.sqlite")
    driver.max_buffered = 0
    output = driver.handle_message(wire(encode_certificate_sync([certificate(transfer(1))])))
    assert output.replies == ()


def test_a_batch_that_taught_something_asks_again(tmp_path):
    driver = driver_at(tmp_path / "a.sqlite")
    output = driver.handle_message(wire(encode_certificate_sync([certificate(transfer(0))])))
    assert [message["type"] for message in output.replies] == ["CERTIFICATE_SYNC_REQUEST"]


@pytest.mark.parametrize("seed", range(8))
def test_a_small_buffer_and_any_order_give_the_same_state(tmp_path, seed):
    # The rule of this file: a limit delays an honest sender and changes nothing else.
    rng = random.Random(seed)
    pay_bob = transfer(0, amount=50)
    events = [
        pay_bob,
        *(transfer(n) for n in range(1, 6)),
        *(transfer(n, sender="bob", receiver="carol") for n in range(5)),
        Transfer("carol", "dave", 1, 0, (pay_bob.event_id(),)),
    ]
    source = driver_at(tmp_path / "source.sqlite")
    certificates = [certificate(event) for event in events]

    for item in certificates:
        source._accept(item)

    assert source._buffer == {}
    arrival = certificates[:]
    rng.shuffle(arrival)
    driver = driver_at(tmp_path / "other.sqlite", 1)
    driver.max_buffered = rng.randint(0, 2)
    driver.max_nonce_ahead = rng.choice((None, 1))

    for item in arrival:
        driver._accept(item)

    # Synchronization until nothing is new, as between two real nodes.
    for _ in range(40):
        request = driver.sync_request()
        answer = source.handle_message(wire(request))

        if not answer.replies:
            break

        for message in answer.replies:
            driver.handle_message(wire(message))

    assert driver.replica.state.root() == source.replica.state.root()


# --- Proofs in memory ----------------------------------------------------------------------------


def test_the_public_evidence_is_added_to_and_not_copied(tmp_path):
    # Before: 1.75 ms for each message with 100 000 proofs, which capped the node at about 570.
    [node] = quorum_nodes(tmp_path, "evidence")

    try:
        before = node.signed_events
        signed = SignedTransfer.create(SENDER, transfer(0))
        node._quorum.driver.handle_message(wire(encode_vote_request(signed)))

        with node._state_lock:
            node._publish_quorum_state()

        assert node.signed_events is before
        assert signed.transfer.event_id() in node.signed_events

        with node._state_lock:
            node._publish_quorum_state()

        assert node._quorum.driver.new_signed_events() == {}
    finally:
        node.stop()


def test_a_proof_of_equivocation_is_published_once(tmp_path):
    [node] = quorum_nodes(tmp_path, "evidence-proof")

    try:
        for receiver in ("x", "y"):
            signed = SignedTransfer.create(SENDER, transfer(0, receiver=receiver))
            node._quorum.driver.handle_message(wire(encode_vote_request(signed)))

        with node._state_lock:
            node._publish_quorum_state()

        assert node._quorum.driver.equivocations
        assert node._quorum.driver.new_equivocations() == []
        assert not node.conflicted
    finally:
        node.stop()


def test_a_driver_built_again_starts_the_evidence_again(tmp_path):
    [node] = quorum_nodes(tmp_path, "evidence-rebuild")

    try:
        signed = SignedTransfer.create(SENDER, transfer(0))
        node._quorum.driver.handle_message(wire(encode_vote_request(signed)))

        with node._state_lock:
            node._publish_quorum_state()

        assert node.signed_events
        with node._state_lock:
            node._quorum._rebuild()
            node._publish_quorum_state()

        assert node.signed_events == {}
    finally:
        node.stop()


# --- Votes being collected --------------------------------------------------------------------------


def test_no_more_events_are_started_past_the_limit(tmp_path):
    driver = driver_at(tmp_path / "a.sqlite")
    driver.max_aggregating = 1
    assert driver.submit(SignedTransfer.create(SENDER, transfer(0))).broadcasts
    assert driver.submit(SignedTransfer.create(SENDER, transfer(1))).broadcasts == ()
    # What is being collected can be sent again.
    assert driver.submit(SignedTransfer.create(SENDER, transfer(0))).broadcasts
