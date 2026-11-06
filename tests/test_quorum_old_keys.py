"""Keys of a committee that has ended are worth little to a thief: `QuorumOldKeys.lean`.

Before this rule, with the keys of an ended committee, stolen after its closure, a certificate for a
spend the sender never signed was executed by nodes of later epochs. Changing committee protected
nothing against stolen keys. This is the attack, on the real code.
"""

import pytest

from core.attestation import Committee, EpochChange, QuorumCertificate, Vote
from core.event import Transfer
from core.signed_event import SignedTransfer
from crypto.identity import Identity
from network.message import encode_certificate, encode_certificate_sync, encode_epoch_closure, encode_vote_request
from network.quorum import VoteStoreError
from sdk.client import ChainVerifier
from tests.test_quorum_reports import (
    CHANGE,
    COMMITTEE,
    GENESIS,
    GOVERNANCE,
    MEMBERS,
    SENDER,
    SIGNERS,
    Cluster,
    wire,
)


def forged(event, committee=COMMITTEE, epoch=0):
    votes = tuple(Vote.create(committee, member, event) for member in MEMBERS[:3])
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


def balance(cluster, index, account):
    return cluster.drivers[index].replica.state.balance(account)


def test_a_certificate_of_stolen_old_keys_is_not_executed(cluster):
    close(cluster)
    evil = forged(spend(receiver="mallory", amount=50))
    assert evil.verify(COMMITTEE)
    assert not cluster.drivers[1].replica.certificate_is_valid(evil)
    cluster.drivers[1].handle_message(wire(encode_certificate(evil)))
    assert balance(cluster, 1, "mallory") == 0


def test_nor_through_synchronization(cluster):
    close(cluster)
    evil = forged(spend(receiver="mallory", amount=50))
    cluster.drivers[1].handle_message(wire(encode_certificate_sync([evil])))
    assert balance(cluster, 1, "mallory") == 0


def test_nor_a_second_spend_after_a_real_one(cluster):
    # The real event of the sender stands.
    event = spend()
    for index in range(4):
        cluster.drivers[index].handle_message(wire(encode_vote_request(signed(event))))
    real = forged(event)
    for index in range(4):
        cluster.drivers[index].handle_message(wire(encode_certificate(real)))
    close(cluster)
    assert balance(cluster, 2, "bob") == 1
    evil = forged(spend(receiver="mallory", amount=50))
    cluster.drivers[2].handle_message(wire(encode_certificate(evil)))
    assert balance(cluster, 2, "mallory") == 0
    assert not cluster.drivers[2].halted


def test_a_real_old_certificate_arriving_late_is_taken(cluster):
    # It formed in epoch 0, and this node hears of it only after the closure.
    event = spend()
    for index in (0, 1, 2):
        cluster.drivers[index].handle_message(wire(encode_vote_request(signed(event))))
    close(cluster)
    late = forged(event)
    assert cluster.drivers[3].replica.certificate_is_valid(late)
    cluster.drivers[3].handle_message(wire(encode_certificate(late)))
    assert balance(cluster, 3, "bob") == 1


def test_a_certificate_of_the_committee_in_force_needs_no_lock(cluster):
    close(cluster)
    committee = cluster.drivers[0].committee
    event = spend()
    certificate = forged(event, committee, 1)
    assert cluster.drivers[1].replica.certificate_is_valid(certificate)
    cluster.drivers[1].handle_message(wire(encode_certificate(certificate)))
    assert balance(cluster, 1, "bob") == 1


def test_a_certificate_of_the_committee_in_force_with_a_conflict_still_halts(cluster):
    close(cluster)
    committee = cluster.drivers[0].committee
    driver = cluster.drivers[1]
    driver.handle_message(wire(encode_certificate(forged(spend(), committee, 1))))
    driver.handle_message(wire(encode_certificate(forged(spend(receiver="carol"), committee, 1))))
    assert driver.halted


def test_two_locked_versions_with_stolen_keys_do_not_halt_a_node(cluster):
    # A sender that signed two versions, both reported: the limit stated in `QuorumOldKeys.lean`.
    first, second = spend(), spend(receiver="carol")
    cluster.drivers[0].handle_message(wire(encode_vote_request(signed(first))))
    cluster.drivers[1].handle_message(wire(encode_vote_request(signed(second))))
    close(cluster)
    driver = cluster.drivers[2]
    driver.handle_message(wire(encode_certificate(forged(first))))
    assert balance(cluster, 2, "bob") == 1
    driver.handle_message(wire(encode_certificate(forged(second))))
    assert balance(cluster, 2, "carol") == 0
    assert not driver.halted


def test_the_log_of_a_node_replays_whatever_the_locks_say(cluster):
    # What ran before a closure stays, even if the closure does not list it, which needs more than
    # f faulty validators. The node must still open, and its state must not change.
    event = spend()
    certificate = forged(event)
    cluster.drivers[3].handle_message(wire(encode_certificate(certificate)))
    assert balance(cluster, 3, "bob") == 1
    close(cluster)
    assert not cluster.stores[3].is_locked_event(event)
    cluster.restart(3)
    assert balance(cluster, 3, "bob") == 1
    assert cluster.drivers[3].committee.epoch == 1


def test_a_lock_is_this_very_event(cluster):
    event = spend()
    cluster.drivers[0].handle_message(wire(encode_vote_request(signed(event))))
    close(cluster)
    store = cluster.stores[1]
    assert store.is_locked_event(event)
    assert not store.is_locked_event(spend(receiver="carol"))
    assert not store.is_locked_event(spend(nonce=1))


def test_a_light_client_applies_the_same_rule(cluster):
    event = spend()
    cluster.drivers[0].handle_message(wire(encode_vote_request(signed(event))))
    close(cluster)
    verifier = ChainVerifier(COMMITTEE, GOVERNANCE)
    closure = cluster.stores[0].closures()[0]
    evil = forged(spend(receiver="mallory"))

    # Without the closures it cannot know: this is the limit stated in `verify`.
    assert verifier.verify(evil)

    verifier.add_closures([encode_epoch_closure(closure)["closure"]])
    assert not verifier.verify(evil)
    assert verifier.verify(forged(event))
    assert verifier.verify(forged(spend(receiver="carol"), cluster.drivers[0].committee, 1))
