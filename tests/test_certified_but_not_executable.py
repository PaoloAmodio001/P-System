"""A valid certificate is not an executable event.

`QuorumReplica.handle_certificate` runs a certificate only when the event is fresh, causally
ready and executable on the current state. The driver keeps one that cannot run yet in its
buffer and retries it after anything else runs. This file separates the two outcomes that
matter to an operator: a temporary wait, which a later event can end, and a permanent one,
where the event can never run and the sender's nonce stays blocked.
"""

import pytest

from core.event import Transfer
from network.message import encode_certificate, encode_vote_request
from tests.test_quorum_driver import Cluster, OTHER, PAYER, signed

A = Transfer(PAYER, "bob", 8, 0)
FUTURE = Transfer(PAYER, "bob", 1, 1, (A.event_id(),))
ZERO = Transfer(PAYER, "bob", 0, 0)
SELF = Transfer(PAYER, PAYER, 1, 0)


@pytest.fixture
def cluster(tmp_path):
    made = Cluster(tmp_path / "votes.sqlite")
    yield made
    made.store.close()


def buffered(cluster):
    return [certificate.event for certificate in cluster.driver._buffer.values()]


def test_a_missing_parent_waits_and_then_runs(cluster):
    cluster.driver.handle_message(cluster.certificate_message(FUTURE))

    assert cluster.executed() == []
    assert buffered(cluster) == [FUTURE]
    assert not cluster.driver.halted

    cluster.driver.handle_message(cluster.certificate_message(A))

    assert cluster.executed() == [A.canonical(), FUTURE.canonical()]
    assert buffered(cluster) == []


def test_insufficient_funds_wait_and_then_run(cluster):
    spend = Transfer(OTHER.identity_id, "dave", 15, 0)
    fund = Transfer(PAYER, OTHER.identity_id, 8, 0)

    cluster.driver.handle_message(cluster.certificate_message(spend))

    assert cluster.executed() == []
    assert buffered(cluster) == [spend]
    assert not cluster.driver.halted

    cluster.driver.handle_message(cluster.certificate_message(fund))

    assert cluster.executed() == [fund.canonical(), spend.canonical()]
    assert buffered(cluster) == []


@pytest.mark.parametrize(
    "event",
    [
        pytest.param(ZERO, id="amount zero"),
        pytest.param(SELF, id="transfer to self"),
    ],
)
def test_an_honest_validator_refuses_to_vote_for_a_permanent_event(cluster, event):
    request = signed(event)

    assert cluster.driver.replica.handle_vote_request(event, request) is None
    assert cluster.driver.replica.votes() == []
    assert cluster.driver.handle_message(encode_vote_request(request)).broadcasts == ()


@pytest.mark.parametrize(
    "event",
    [
        pytest.param(ZERO, id="amount zero"),
        pytest.param(SELF, id="transfer to self"),
    ],
)
def test_a_permanent_certificate_is_dropped_and_the_nonce_still_moves(cluster, event):
    # A quorum forged, or formed on votes from a version without the vote check. Keeping it
    # would block the sender's nonce for good, so the driver drops it.
    assert cluster.certificate(event, 1, 2, 3).verify(cluster.committee)

    cluster.driver.handle_message(cluster.certificate_message(event))

    assert cluster.executed() == []
    assert buffered(cluster) == []
    assert not cluster.driver.halted

    cluster.driver.handle_message(cluster.certificate_message(A))

    assert cluster.executed() == [A.canonical()]
    assert buffered(cluster) == []


def test_a_rejected_signature_of_the_same_nonce_does_not_block_it(cluster):
    forged = Transfer(PAYER, "mallory", 1, 0)
    cluster.driver.handle_message(
        encode_certificate(
            cluster.certificate(forged, 1, 2)
        )
    )

    assert buffered(cluster) == []
    assert cluster.driver.handle_message(cluster.certificate_message(A)).broadcasts == ()
    assert cluster.executed() == [A.canonical()]
