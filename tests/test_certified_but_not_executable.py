"""A valid certificate is not an executable event.

Aligned to the Lean model (formal/lean/PSystem/Quorum.lean, voteRequest/step)
in session 5: voting depends on `auth && voteAllowed`, not on static
executability (`executableBool` applies at certificate execution). A
statically non-executable event (e.g. amount=0, sender=receiver) may be voted
on; a valid certificate for it is accepted as known but never executed.

`QuorumReplica.handle_certificate`/driver execute a certificate only when valid,
executable on the current state, causally ready and not already executed. A
statically non-executable certificate never executes; it is tracked as known
(idempotent/conflict-detectable) without blocking execution progress via the
buffer.
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
def test_an_honest_validator_votes_for_a_statically_non_executable_event(cluster, event):
    """Lean spec: voteRequest admits by auth && voteAllowed (no executableBool)."""
    request = signed(event)

    vote = cluster.driver.replica.handle_vote_request(event, request)
    assert vote is not None
    assert cluster.driver.replica.votes() == [event]
    response = cluster.driver.handle_message(encode_vote_request(request))
    assert response.replies != () or response.broadcasts != ()


@pytest.mark.parametrize(
    "event",
    [
        pytest.param(ZERO, id="amount zero"),
        pytest.param(SELF, id="transfer to self"),
    ],
)
def test_a_statically_non_executable_certificate_is_known_but_not_executed(cluster, event):
    """Lean spec: cert execution requires executableBool; a valid cert for a
    statically non-executable event is accepted as known but never executed, and
    the executed-state nonce does not advance."""
    assert cluster.certificate(event, 1, 2, 3).verify(cluster.committee)

    cluster.driver.handle_message(cluster.certificate_message(event))

    assert cluster.executed() == []
    assert buffered(cluster) == []
    assert not cluster.driver.halted
    assert cluster.driver.replica.state.nonce(PAYER) == 0


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
