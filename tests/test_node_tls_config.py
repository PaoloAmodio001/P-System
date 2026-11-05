"""A node's TLS identity comes from outside, and is checked against what the peer claims."""

import socket
import time

import pytest

from core.state import State
from network.handshake import Handshake
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
    first = Node("a-node", State(), tls_config=config_for(authority, "a-node", tmp_path))
    second = Node("b-node", State(), tls_config=config_for(authority, "b-node", tmp_path))
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
    first = Node("a-node", State(), tls_config=config_for(authority, "a-node", tmp_path))
    second = Node(
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
    node = Node("victim", State(), tls_config=config_for(authority, "victim", tmp_path))
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
    node = Node("victim", State(), tls_config=config_for(authority, "victim", tmp_path))
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
    first = Node("a-node", State(), tls_config=config_for(authority, "a-node", tmp_path))
    second = Node(
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
    first = Node("a-node", State())
    second = Node("b-node", State())
    first.start()
    second.start()
    try:
        host, port = second.address()
        assert first.connect_peer(Peer(node_id="b-node", host=host, port=port))
    finally:
        first.stop()
        second.stop()
