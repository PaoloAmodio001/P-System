"""An event of an honest sender that stopped with every node up, and what prevents it.

Measured in docs/piano-bizantino.md. The node with the lower id called back a peer that had already called it,
and closed the connection in use: what was queued, in flight or still to be answered on it was lost, and
nothing sent it again. These tests stage that moment with proxies, so that they do not depend on timing.
"""

import dataclasses
import random
import socket
import time

import pytest

from core.state import State
from crypto.identity import Identity
from network.handshake import Handshake
from network.node import Node
from network.peer import Peer
from network.peer_connection import PeerConnection
from scripts import measure_network as measure
from scripts.probe_stuck_event import established_links
from sdk.client import Client
from tests.chaos import ChaosDeployment
from tests.deployment_helpers import wait_until
from tests.test_quorum_node import GENESIS, Committee4

BURST = 50
# Longer than a node waits between two tries of a peer that cannot be reached.
A_CALL_BACK_WOULD_HAVE_COME = 3.0


def peer_of(node: Node) -> Peer:
    return Peer(node_id=node.node_id, host="127.0.0.1", port=node.port)


# --- The call back ---------------------------------------------------------------------------------


def test_a_live_connection_from_the_higher_id_is_not_replaced():
    lower, higher = Node("a-node", State()), Node("z-node", State())

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
    left, right = Node("a-node", State()), Node("z-node", State())

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
