"""A node's TLS identity comes from outside, and is checked against what the peer claims."""

import socket
import time

import pytest

from core.state import State
from network.handshake import Handshake
from tests.node_helpers import standalone_node
from network.node import Node
from network.node_tls_identity import issue_node_certificate, create_authority
from network.peer import Peer
from network.secure_transport import SecureTransport


def wait_until(condition, seconds=5.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return condition()


@pytest.fixture
def authority(tmp_path):
    return create_authority(tmp_path / "ca")


def config_for(authority, node_id, tmp_path):
    return issue_node_certificate(authority, node_id, tmp_path / "nodes")


def test_nodes_with_certificates_of_one_authority_connect(authority, tmp_path):
    first = standalone_node("a-node", State(), tls_config=config_for(authority, "a-node", tmp_path))
    second = standalone_node("b-node", State(), tls_config=config_for(authority, "b-node", tmp_path))
    first.start()
    second.start()
    try:
        host, port = second.address()
        assert first.connect_peer(Peer(node_id="b-node", host=host, port=port))
        assert wait_until(lambda: "a-node" in second.peer_connections)
    finally:
        first.stop()
        second.stop()


def test_node_of_another_authority_cannot_connect(authority, tmp_path):
    other = create_authority(tmp_path / "other-ca")
    first = standalone_node("a-node", State(), tls_config=config_for(authority, "a-node", tmp_path))
    second = standalone_node(
        "b-node",
        State(),
        tls_config=issue_node_certificate(other, "b-node", tmp_path / "other"),
    )
    first.start()
    second.start()
    try:
        host, port = second.address()
        assert not first.connect_peer(Peer(node_id="b-node", host=host, port=port))
        assert second.peer_connections == {}
    finally:
        first.stop()
        second.stop()


def _handshake_as(config, claimed_id, node):
    host, port = node.address()
    raw = socket.create_connection((host, port), timeout=3)
    connection = SecureTransport.wrap_client(
        raw,
        SecureTransport.create_client_context(config),
        node.node_id,
    )
    SecureTransport.send(connection, Handshake(claimed_id, "127.0.0.1", 1).encode())
    return connection


def test_a_peer_cannot_claim_the_node_id_of_another_certificate(authority, tmp_path):
    # Holding a certificate of the authority is not being every node of it: this used to
    # replace the connection of the real peer.
    node = standalone_node("victim", State(), tls_config=config_for(authority, "victim", tmp_path))
    node.start()
    try:
        connection = _handshake_as(config_for(authority, "mallory", tmp_path), "honest-peer", node)
        with pytest.raises((ConnectionError, OSError)):
            connection.settimeout(3)
            SecureTransport.receive(connection)
        assert "honest-peer" not in node.peer_connections
        assert "honest-peer" not in node.peers
        connection.close()
    finally:
        node.stop()


def test_a_peer_with_its_own_certificate_is_accepted_under_its_name(authority, tmp_path):
    node = standalone_node("victim", State(), tls_config=config_for(authority, "victim", tmp_path))
    node.start()
    try:
        connection = _handshake_as(config_for(authority, "peer-x", tmp_path), "peer-x", node)
        connection.settimeout(3)
        assert SecureTransport.receive(connection)["node_id"] == "victim"
        assert wait_until(lambda: "peer-x" in node.peer_connections)
        connection.close()
    finally:
        node.stop()


def test_private_keys_are_readable_only_by_their_owner(authority, tmp_path):
    config = config_for(authority, "a-node", tmp_path)
    from pathlib import Path

    assert Path(config.private_key).stat().st_mode & 0o077 == 0
    assert (authority.directory / "ca.key").stat().st_mode & 0o077 == 0


def test_an_authority_can_be_loaded_again(authority, tmp_path):
    from network.node_tls_identity import load_authority

    again = load_authority(authority.directory)
    first = standalone_node("a-node", State(), tls_config=config_for(authority, "a-node", tmp_path))
    second = standalone_node(
        "b-node",
        State(),
        tls_config=issue_node_certificate(again, "b-node", tmp_path / "later"),
    )
    first.start()
    second.start()
    try:
        host, port = second.address()
        assert first.connect_peer(Peer(node_id="b-node", host=host, port=port))
    finally:
        first.stop()
        second.stop()


def test_without_a_config_a_node_still_works_inside_one_process():
    first = standalone_node("a-node", State())
    second = standalone_node("b-node", State())
    first.start()
    second.start()
    try:
        host, port = second.address()
        assert first.connect_peer(Peer(node_id="b-node", host=host, port=port))
    finally:
        first.stop()
        second.stop()


def _node_on_all_interfaces(authority, tmp_path, name):
    return standalone_node(name, State(), host="0.0.0.0", tls_config=config_for(authority, name, tmp_path))


def test_a_node_on_all_interfaces_stays_reachable_at_the_address_it_was_dialed(authority, tmp_path):
    # It announces 0.0.0.0, which means nothing to a peer. Taking that as its address broke
    # every reconnection on a real network.
    first = _node_on_all_interfaces(authority, tmp_path, "a-node")
    second = _node_on_all_interfaces(authority, tmp_path, "b-node")
    first.start()
    second.start()
    try:
        _, port = second.address()
        assert first.connect_peer(Peer(node_id="b-node", host="127.0.0.1", port=port))
        assert first.peers["b-node"].host == "127.0.0.1"
        assert wait_until(lambda: "a-node" in second.peers)
        assert second.peers["a-node"].host == "127.0.0.1"
    finally:
        first.stop()
        second.stop()


def test_a_reconnection_works_after_a_peer_on_all_interfaces_goes_away(authority, tmp_path):
    first = _node_on_all_interfaces(authority, tmp_path, "a-node")
    second = _node_on_all_interfaces(authority, tmp_path, "b-node")
    first.start()
    second.start()
    _, port = second.address()
    assert first.connect_peer(Peer(node_id="b-node", host="127.0.0.1", port=port))
    assert wait_until(lambda: "a-node" in second.peer_connections)
    second.stop()
    assert wait_until(lambda: "b-node" not in first.peer_connections)
    assert first.peers["b-node"].host == "127.0.0.1"
    first.stop()


def test_a_connection_on_its_way_counts_as_connected():
    # The rule for dialing at once keeps the connection of the lower id. Seen from the higher id,
    # its own works, then goes, and the other is on its way. Timing made this rare, and
    # tests/test_peer_connection_race_real.py found it under load, so the moment is staged here.
    import threading

    higher = standalone_node("z-node", State())

    class Incoming:
        connected = True
        initiated_locally = False

        def close(self):
            pass

    timer = threading.Timer(0.1, lambda: higher.peer_connections.update({"a-node": Incoming()}))
    timer.start()
    assert higher._wait_for_connection_from(Peer(node_id="a-node", host="x", port=1))
    higher.peer_connections.clear()
    higher.stop()


def test_the_lower_id_does_not_wait_for_a_connection_that_will_not_come():
    lower = standalone_node("a-node", State())
    started = time.monotonic()
    assert not lower._wait_for_connection_from(Peer(node_id="z-node", host="x", port=1))
    assert time.monotonic() - started < 0.5
    lower.stop()


def test_a_connection_this_node_started_is_not_the_one_it_waits_for(monkeypatch):
    monkeypatch.setattr(Node, "SIMULTANEOUS_DIAL_SECONDS", 0.1)
    higher = standalone_node("z-node", State())

    class Outgoing:
        connected = True
        initiated_locally = True

        def close(self):
            pass

    higher.peer_connections["a-node"] = Outgoing()
    assert not higher._wait_for_connection_from(Peer(node_id="a-node", host="x", port=1))
    higher.peer_connections.clear()
    higher.stop()
