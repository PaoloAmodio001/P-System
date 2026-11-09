"""Stolen keys of an ended committee and two versions the sender really signed.

`docs/PROTOCOL.md`:79-82 and `QuorumOldKeys.lean` state the limit: a node ignores a
conflicting certificate of an ended committee, so stolen keys cannot halt it, but if the sender
signed two versions and both are in the locks, the wrong one can be taken. This file records
that case across a restart: the first version stands, the second stays out, and the node does
not turn the absence of a provable conflict into a halt.
"""

import pytest

from core.attestation import QuorumCertificate, Vote
from core.event import Transfer
from core.signed_event import SignedTransfer
from network.message import encode_certificate, encode_vote_request
from tests.test_quorum_reports import CHANGE, COMMITTEE, MEMBERS, SENDER, Cluster, wire


def forged(event, epoch=0):
    votes = tuple(Vote.create(COMMITTEE, member, event) for member in MEMBERS[:3])
    return QuorumCertificate(event, votes, epoch)


def spend(nonce=0, receiver="bob", amount=1):
    return Transfer(SENDER.identity_id, receiver, amount, nonce)


def signed(event):
    return SignedTransfer.create(SENDER, event)


def close(cluster):
    output = cluster.drivers[0].propose_epoch_change(CHANGE)
    for message in output.broadcasts:
        cluster.deliver(0, message, [1, 2, 3])
    assert cluster.epochs() == [1, 1, 1, 1]


@pytest.fixture
def cluster(tmp_path):
    made = Cluster(tmp_path)
    yield made
    made.close()


def test_two_locked_versions_stay_out_and_do_not_halt(cluster):
    first, second = spend(), spend(receiver="carol")
    cluster.drivers[0].handle_message(wire(encode_vote_request(signed(first))))
    cluster.drivers[1].handle_message(wire(encode_vote_request(signed(second))))
    close(cluster)
    driver = cluster.drivers[2]

    driver.handle_message(wire(encode_certificate(forged(first))))
    driver.handle_message(wire(encode_certificate(forged(second))))

    assert cluster.drivers[2].replica.state.balance("bob") == 1
    assert cluster.drivers[2].replica.state.balance("carol") == 0
    assert not driver.halted


def test_the_first_version_stands_after_a_restart(cluster):
    first, second = spend(), spend(receiver="carol")
    cluster.drivers[0].handle_message(wire(encode_vote_request(signed(first))))
    cluster.drivers[1].handle_message(wire(encode_vote_request(signed(second))))
    close(cluster)

    cluster.drivers[2].handle_message(wire(encode_certificate(forged(first))))
    cluster.drivers[2].handle_message(wire(encode_certificate(forged(second))))
    cluster.restart(2)

    driver = cluster.drivers[2]
    assert driver.replica.state.balance("bob") == 1
    assert driver.replica.state.balance("carol") == 0
    assert driver.committee.epoch == 1
    assert not driver.halted

    driver.handle_message(wire(encode_certificate(forged(second))))

    assert driver.replica.state.balance("carol") == 0
    assert not driver.halted
