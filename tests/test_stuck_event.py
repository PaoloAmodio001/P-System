"""An event of an honest sender that stopped with every node up, and what prevents it.

Measured in archive/docs/piano-bizantino.md. The node with the lower id called back a peer that had already called it,
and closed the connection in use: what was queued, in flight or still to be answered on it was lost, and
nothing sent it again. These tests stage that moment with proxies, so that they do not depend on timing.
"""

import dataclasses
import random
import socket
import time

import pytest

from core.attestation import Vote
from core.event import Transfer
from core.signed_event import SignedTransfer
from core.state import State
from crypto.identity import Identity
from network.handshake import Handshake
from network.message import decode_vote_request, encode_certificate, encode_vote, encode_vote_request
from tests.node_helpers import standalone_node
from network.node import Node
from network.peer import Peer
from network.peer_connection import PeerConnection
from network.quorum import QuorumDriver, QuorumReplica, SqliteVoteStore
from scripts import measure_network as measure
from scripts.probe_stuck_event import established_links
from sdk.client import Client
from tests.chaos import ChaosDeployment
from tests.deployment_helpers import wait_until
from tests.failure_evidence import ROOT, failures_directory
from tests.test_quorum_node import GENESIS, PAYER, Committee4, signed

from network.quorum.rounds import RoundDriver


@pytest.fixture(autouse=True)
def _no_round_timeouts(monkeypatch):
    # These tests are about asking again; the rounds that follow a split have their own tests.
    monkeypatch.setattr(RoundDriver, "ROUND_FIRST_SECONDS", float("inf"))
    monkeypatch.setattr(RoundDriver, "ROUND_LONGEST_SECONDS", float("inf"))


BURST = 50
# Longer than a node waits between two tries of a peer that cannot be reached.
A_CALL_BACK_WOULD_HAVE_COME = 3.0
# A thread of a proxy already in `recv` when its link stalls still forwards what it gets: 0.2 s at most.
UNTIL_A_STALL_HOLDS = 0.3


def peer_of(node: Node) -> Peer:
    return Peer(node_id=node.node_id, host="127.0.0.1", port=node.port)


# --- The call back ---------------------------------------------------------------------------------


def test_a_live_connection_from_the_higher_id_is_not_replaced():
    lower, higher = standalone_node("a-node", State()), standalone_node("z-node", State())

    try:
        lower.start()
        higher.start()
        assert higher.connect_peer(peer_of(lower))
        assert wait_until(lambda: "z-node" in lower.peer_connections, 5)
        in_use = lower.peer_connections["z-node"]
        assert not in_use.initiated_locally
        # What the service does: every node knows every peer, and its reconnect loop looks after them.
        lower.add_peer(peer_of(higher))
        time.sleep(A_CALL_BACK_WOULD_HAVE_COME)
        assert lower.peer_connections["z-node"] is in_use
        assert in_use.connected
    finally:
        lower.stop()
        higher.stop()


def agree(left: Node, right: Node) -> bool:
    """Each holds a live connection to the other, and they are the two ends of one."""
    mine = left.peer_connections.get(right.node_id)
    theirs = right.peer_connections.get(left.node_id)
    return (
        mine is not None
        and theirs is not None
        and mine.connected
        and theirs.connected
        and mine.initiated_locally != theirs.initiated_locally
    )


@pytest.mark.parametrize("round_number", range(5))
def test_two_nodes_that_call_each_other_end_on_one_connection(round_number):
    # What the rule of the lower id is for, and it stays. Here the reconnect loops call, as in the service.
    left, right = standalone_node("a-node", State()), standalone_node("z-node", State())

    try:
        left.start()
        right.start()
        left.add_peer(peer_of(right))
        right.add_peer(peer_of(left))
        assert wait_until(lambda: agree(left, right), 10)
        kept = left.peer_connections["z-node"]
        # And it stays on that one, or this would be the same trouble, later.
        time.sleep(A_CALL_BACK_WOULD_HAVE_COME)
        assert left.peer_connections["z-node"] is kept
        assert agree(left, right)
    finally:
        left.stop()
        right.stop()


def test_a_dead_connection_from_the_higher_id_does_not_keep_it_out(tmp_path):
    # What the call back did besides: it replaced a connection that had died without a word. The node
    # refuses a new connection while it thinks it has one, and that ends with its next write, since the
    # synchronization writes all the time. Only for a node with a synchronization: see the plan.
    four = Committee4(tmp_path)
    lower = Node("a-node", GENESIS, quorum=dataclasses.replace(four.config(0), sync_interval=0.1))
    higher = Node("z-node", GENESIS, quorum=dataclasses.replace(four.config(1), sync_interval=0.1))
    near, far = socket.socketpair()

    try:
        lower.start()
        higher.start()
        dead = PeerConnection.adopt("a-node", near, Handshake(node_id="z-node", host="127.0.0.1", port=1))
        dead.on_disconnect = lower._peer_disconnected
        assert lower._register_peer_connection("z-node", dead)
        lower.add_peer(peer_of(higher))
        far.close()
        higher.add_peer(peer_of(lower))
        assert wait_until(lambda: agree(lower, higher), 15)
        assert lower.peer_connections["z-node"] is not dead
    finally:
        lower.stop()
        higher.stop()


@pytest.fixture
def proxied(tmp_path):
    made = ChaosDeployment(tmp_path, random.Random(7))
    yield made
    made.close()


def links_of(made) -> set:
    return established_links(set(made.ports))


def test_a_burst_is_not_lost_to_a_call_back(proxied):
    # Nodes 2 and 3 called the first node, which cannot call them. A burst is on its way on those two
    # connections when the first node becomes able to call them: before the correction it did, it closed
    # both, and every event stopped. All the nodes then see each other and no fault remains.
    made = proxied

    for peer in (2, 3):
        made.links[(0, peer)].blocked = True

    made.start_all()
    clients = [Client(made.api_url(index)) for index in range(made.count)]
    measure.wait_connected(clients)
    # A node may still have been dialing, and that is another thing: the other node's rule, not a call back.
    time.sleep(A_CALL_BACK_WOULD_HAVE_COME)
    before = links_of(made)

    for peer in (2, 3):
        made.links[(peer, 0)].stalled = True

    time.sleep(UNTIL_A_STALL_HOLDS)
    sender = measure.Sender(Identity.load(made.sender_key))
    clients[0].submit_many([sender.next() for _ in range(BURST)])

    for peer in (2, 3):
        made.links[(0, peer)].blocked = False

    time.sleep(A_CALL_BACK_WOULD_HAVE_COME)
    same = links_of(made) >= before

    for peer in (2, 3):
        made.links[(peer, 0)].stalled = False

    # In this order: the event stopped is what a user sees. With the rest of the correction it would run
    # all the same, sent again, and then the second line is what still says that nothing was replaced.
    measure.wait_for(clients, sender.identity.identity_id, BURST, 20.0)
    assert same, "A CONNECTION IN USE WAS REPLACED"


# --- Asking again ----------------------------------------------------------------------------------


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


class Drivers:
    """The drivers of a committee of real keys, with no network: a test carries the messages."""

    def __init__(self, directory):
        self.clock = Clock()
        self.four = Committee4(directory)
        self.stores = []
        self.drivers = []

        for index, member in enumerate(self.four.members):
            store = SqliteVoteStore(
                directory / f"driver-{index}.sqlite",
                self.four.committee,
                member.public_key,
                create=True,
            )
            self.stores.append(store)
            self.drivers.append(
                QuorumDriver(QuorumReplica(member, GENESIS, store, lambda _: True), clock=self.clock)
            )

    @property
    def first(self) -> QuorumDriver:
        return self.drivers[0]

    def at(self, seconds: float) -> list[dict]:
        self.clock.now = 100.0 + seconds
        return list(self.first.retry().broadcasts)

    def close(self) -> None:
        for store in self.stores:
            store.close()


@pytest.fixture
def drivers(tmp_path):
    made = Drivers(tmp_path)
    yield made
    made.close()


def requested(messages: list[dict]) -> list[int]:
    return [decode_vote_request(message).transfer.nonce for message in messages]


def transfer(nonce: int) -> SignedTransfer:
    return signed(Transfer(PAYER, "bob", 1, nonce))


FIRST = QuorumDriver.RESEND_FIRST_SECONDS
LONGEST = QuorumDriver.RESEND_LONGEST_SECONDS
MOST = QuorumDriver.RESEND_MOST_IN_A_ROUND


def test_an_event_is_not_asked_for_again_too_soon(drivers):
    drivers.first.submit(transfer(0))
    assert drivers.at(FIRST - 0.1) == []


def test_an_event_with_no_certificate_is_asked_for_again_as_it_was_signed(drivers):
    event = transfer(0)
    drivers.first.submit(event)
    assert drivers.at(FIRST) == [encode_vote_request(event)]


def test_each_wait_is_twice_the_last_up_to_the_longest(drivers):
    drivers.first.submit(transfer(0))
    now = FIRST
    assert requested(drivers.at(now)) == [0]
    wait = 2 * FIRST

    while wait < LONGEST:
        assert drivers.at(now + wait - 0.1) == []
        now += wait
        assert requested(drivers.at(now)) == [0]
        wait *= 2

    assert drivers.at(now + LONGEST - 0.1) == []
    assert requested(drivers.at(now + LONGEST)) == [0]
    assert drivers.at(now + LONGEST + LONGEST - 0.1) == []


def test_a_round_asks_for_no_more_than_the_limit_and_the_rest_comes_next(drivers):
    for nonce in range(MOST + 10):
        drivers.first.submit(transfer(nonce))

    assert requested(drivers.at(FIRST)) == list(range(MOST))
    assert requested(drivers.at(FIRST + 0.1)) == list(range(MOST, MOST + 10))


def test_events_that_never_get_a_quorum_do_not_take_the_turn_of_the_others(drivers):
    # The one waiting longest goes first, whatever its nonce. By nonce alone, as many events as a
    # round can hold with lower nonces would keep this one out for as long as they keep failing.
    drivers.first.submit(transfer(MOST))
    drivers.clock.now = 100.0 + 0.5

    for nonce in range(MOST):
        drivers.first.submit(transfer(nonce))

    assert requested(drivers.at(FIRST + 0.5)) == [MOST, *range(MOST - 1)]


def test_nothing_is_asked_for_once_the_votes_make_a_certificate(drivers):
    event = transfer(0)
    drivers.first.submit(event)

    for index in (1, 2):
        vote = Vote.create(drivers.four.committee, drivers.four.members[index], event.transfer)
        drivers.first.handle_message(encode_vote(event.transfer, vote))

    assert drivers.at(FIRST) == []
    assert drivers.first._to_resend == {}


def test_nothing_is_asked_for_once_a_certificate_came_by_another_route(drivers):
    event = transfer(0)
    drivers.first.submit(event)
    drivers.first.handle_message(encode_certificate(drivers.four.certificate(event.transfer)))
    assert drivers.at(FIRST) == []
    assert drivers.first._to_resend == {}
    assert drivers.first._aggregating == {}


def test_nothing_is_asked_for_once_another_version_is_certified(drivers):
    # The sender signed two: one got a certificate elsewhere, and this one never can.
    event = signed(Transfer(PAYER, "bob", 1, 1))
    drivers.first.submit(event)
    other = Transfer(PAYER, "carol", 1, 1)
    drivers.first.handle_message(encode_certificate(drivers.four.certificate(other)))
    assert drivers.at(FIRST) == []
    assert drivers.first._aggregating == {}


def test_nothing_is_asked_for_once_the_votes_are_gone(drivers):
    # What a closure does: votes for an ended committee are no use, and it empties the aggregation.
    drivers.first.submit(transfer(0))
    drivers.first._aggregating.clear()
    assert drivers.at(FIRST) == []


def test_nothing_is_asked_for_after_a_halt(drivers):
    event, other = Transfer(PAYER, "bob", 1, 1), Transfer(PAYER, "carol", 1, 1)
    drivers.first.submit(transfer(0))

    for version in (event, other):
        drivers.first.handle_message(encode_certificate(drivers.four.certificate(version)))

    assert drivers.first.halted
    assert drivers.at(FIRST) == []


def test_a_node_tells_its_driver_of_a_new_connection_once(tmp_path):
    four = Committee4(tmp_path)
    node = four.node(0)

    sent = []

    class Connected:
        connected = True
        initiated_locally = True

        def close(self):
            pass

        def enqueue(self, message):
            sent.append(message)

    try:
        node._quorum.driver.submit(transfer(0))
        node._publish_peer_connection("other", Connected())
        told = []
        ending = node._quorum.driver.resend_soon
        node._quorum.driver.resend_soon = lambda: (told.append(1), ending())
        node._retry_closure()
        node._retry_closure()
        assert told == [1]
        assert requested(sent) == [0]
    finally:
        node.peer_connections.clear()
        four.stop_all()


def test_a_new_connection_ends_the_wait(drivers):
    drivers.first.submit(transfer(0))
    assert requested(drivers.at(FIRST)) == [0]
    drivers.clock.now = 100.0 + FIRST + 0.1
    drivers.first.resend_soon()
    assert requested(drivers.at(FIRST + 0.1)) == [0]
    # And it starts again from the shortest.
    assert drivers.at(FIRST + 0.1 + 2 * FIRST - 0.1) == []
    assert requested(drivers.at(FIRST + 0.1 + 2 * FIRST)) == [0]


def test_lost_votes_make_a_certificate_when_asked_again(drivers):
    event = transfer(0)
    first_request = drivers.first.submit(event).broadcasts[0]

    for peer in drivers.drivers[1:]:
        assert peer.handle_message(first_request).replies  # All these answers are lost.

    assert drivers.first.replica.state.nonce(PAYER) == 0

    for message in drivers.at(FIRST):
        for peer in drivers.drivers[1:]:
            for reply in peer.handle_message(message).replies:
                drivers.first.handle_message(reply)

    assert drivers.first.replica.state.nonce(PAYER) == 1


def test_a_validator_asked_again_answers_the_same_and_votes_for_nothing_else(drivers):
    peer = drivers.drivers[1]
    event = Transfer(PAYER, "bob", 1, 0)
    request = encode_vote_request(signed(event))
    first = peer.handle_message(request).replies
    assert first
    assert peer.handle_message(request).replies == first
    assert [voted.canonical() for voted in peer.replica.votes()] == [event.canonical()]
    other = encode_vote_request(signed(Transfer(PAYER, "carol", 1, 0)))
    assert not peer.handle_message(other).replies
    assert peer.handle_message(request).replies == first


def test_the_same_validator_asked_twice_counts_once(drivers):
    event = transfer(0)
    drivers.first.submit(event)
    reply = drivers.drivers[1].handle_message(encode_vote_request(event)).replies[0]
    drivers.first.handle_message(reply)
    drivers.first.handle_message(reply)
    assert drivers.first.replica.state.nonce(PAYER) == 0
    assert requested(drivers.at(FIRST)) == [0]


def test_a_burst_lost_with_two_connections_runs_all_the_same(proxied):
    # What is on the two connections is lost for certain: nothing moves until they are cut.
    made = proxied
    made.start_all()
    clients = [Client(made.api_url(index)) for index in range(made.count)]
    measure.wait_connected(clients)
    sender = measure.Sender(Identity.load(made.sender_key))
    account = sender.identity.identity_id

    for peer in (1, 2):
        for link in ((0, peer), (peer, 0)):
            made.links[link].stalled = True

    time.sleep(UNTIL_A_STALL_HOLDS)
    clients[0].submit_many([sender.next() for _ in range(BURST)])
    time.sleep(0.5)

    for peer in (1, 2):
        for link in ((0, peer), (peer, 0)):
            made.links[link].cut()
            made.links[link].clear()

    measure.wait_for(clients, account, BURST, 20.0)
    assert len({client.status()["state_root"] for client in clients}) == 1


# --- A certificate that reaches nobody -------------------------------------------------------------


def four_nodes(tmp_path, sync_interval):
    four = Committee4(tmp_path)
    nodes = [
        Node(f"q-{index}", GENESIS, quorum=dataclasses.replace(four.config(index), sync_interval=sync_interval))
        for index in range(4)
    ]
    four.nodes.extend(nodes)

    for node in nodes:
        node.start()

    for node in nodes:
        for other in nodes:
            node.add_peer(peer_of(other))

    assert wait_until(lambda: all(len(node.peer_connections) == 3 for node in nodes), 15)
    return four, nodes


def certificates_are_not_sent(node) -> None:
    send = node._send_quorum_output

    def without_certificates(output, connection):
        kept = tuple(m for m in output.broadcasts if m.get("type") != "CERTIFICATE")
        send(dataclasses.replace(output, broadcasts=kept), connection)

    node._send_quorum_output = without_certificates


def test_a_certificate_nobody_got_comes_with_the_synchronization(tmp_path):
    four, nodes = four_nodes(tmp_path, 0.2)

    try:
        certificates_are_not_sent(nodes[0])
        assert nodes[0].submit(signed(Transfer(PAYER, "bob", 1, 0)))
        assert wait_until(lambda: nodes[0]._quorum.replica.state.nonce(PAYER) == 1, 10)
        assert wait_until(lambda: all(n._quorum.replica.state.nonce(PAYER) == 1 for n in nodes), 15)
        assert len({n._quorum.replica.state.root() for n in nodes}) == 1
    finally:
        four.stop_all()


def test_without_the_synchronization_that_certificate_stays_on_one_node(tmp_path):
    # So the test above can fail: it is the synchronization that brought it, and nothing else.
    four, nodes = four_nodes(tmp_path, None)

    try:
        certificates_are_not_sent(nodes[0])
        assert nodes[0].submit(signed(Transfer(PAYER, "bob", 1, 0)))
        assert wait_until(lambda: nodes[0]._quorum.replica.state.nonce(PAYER) == 1, 10)
        time.sleep(1.5)
        assert [n._quorum.replica.state.nonce(PAYER) for n in nodes[1:]] == [0, 0, 0]
    finally:
        four.stop_all()


def test_without_a_synchronization_a_dead_connection_keeps_a_peer_out(tmp_path):
    # A limit, written down. Nothing here writes, so nothing here finds out. No service runs like this:
    # the configuration of a node has a synchronization, and it must be positive.
    four = Committee4(tmp_path)
    lower = Node("a-node", GENESIS, quorum=dataclasses.replace(four.config(0), sync_interval=None))
    higher = Node("z-node", GENESIS, quorum=dataclasses.replace(four.config(1), sync_interval=None))
    near, far = socket.socketpair()

    try:
        lower.start()
        higher.start()
        dead = PeerConnection.adopt("a-node", near, Handshake(node_id="z-node", host="127.0.0.1", port=1))
        assert lower._register_peer_connection("z-node", dead)
        far.close()
        higher.add_peer(peer_of(lower))
        time.sleep(A_CALL_BACK_WOULD_HAVE_COME)
        assert lower.peer_connections["z-node"] is dead
        assert not agree(lower, higher)
    finally:
        lower.stop()
        higher.stop()


# --- Where the evidence goes -----------------------------------------------------------------------


def test_the_ci_keeps_the_folder_where_a_failure_leaves_its_evidence(monkeypatch):
    monkeypatch.delenv("PSYSTEM_FAILURE_DIR", raising=False)
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    step = workflow[workflow.index("- name: Keep what a failed test left"):]
    assert "if: failure()" in step
    assert "actions/upload-artifact@" in step
    assert "path: test-failures/\n" in step
    assert failures_directory("x").parent == ROOT / "test-failures"
