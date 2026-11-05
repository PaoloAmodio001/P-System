"""QuorumDriver.record_evidence: signed events kept with no vote and no execution."""

import pytest

from core.event import Transfer
from core.signed_event import SignedTransfer
from tests.test_quorum_driver import (
    A,
    B,
    OTHER,
    PAYER,
    SENDER,
    Cluster,
    request,
    signed,
)


@pytest.fixture
def cluster(tmp_path):
    made = Cluster(tmp_path / "votes.sqlite")
    yield made
    made.store.close()


def test_evidence_is_kept_with_no_vote_and_no_execution(cluster):
    assert cluster.driver.record_evidence(signed(A))

    assert cluster.driver.signed_events == {A.event_id(): signed(A)}
    assert cluster.voted() == set()
    assert cluster.executed() == []


def test_evidence_takes_no_vote_lock(cluster):
    cluster.driver.record_evidence(signed(A))

    assert cluster.driver.handle_message(request(B)).replies


@pytest.mark.parametrize(
    "bad",
    [
        pytest.param(
            lambda: SignedTransfer(A, SENDER.public_key, bytes(64)),
            id="invalid signature",
        ),
        pytest.param(lambda: signed(A, OTHER), id="signed by another identity"),
        pytest.param(lambda: signed(Transfer("alias", "bob", 1, 0)), id="alias"),
        pytest.param(lambda: signed(Transfer(PAYER, "bob", -1, 0)), id="malformed"),
    ],
)
def test_what_a_sender_did_not_authorize_is_not_evidence(cluster, bad):
    assert not cluster.driver.record_evidence(bad())
    assert cluster.driver.signed_events == {}


def test_alternatives_by_any_path_make_one_proof(cluster):
    # A vote request and evidence must see each other.
    cluster.driver.handle_message(request(A))
    cluster.driver.record_evidence(signed(B))

    assert cluster.driver.equivocations[(PAYER, 0)].verify()
    assert set(cluster.driver.signed_events) == {A.event_id(), B.event_id()}


def test_submitted_and_requested_events_are_evidence_too(cluster):
    cluster.driver.submit(signed(A))
    other = Transfer(PAYER, "bob", 1, 1, (A.event_id(),))
    cluster.driver.handle_message(request(other))

    assert set(cluster.driver.signed_events) == {A.event_id(), other.event_id()}


def test_first_signed_version_of_an_event_is_kept(cluster):
    cluster.driver.record_evidence(signed(A))
    cluster.driver.record_evidence(signed(A))

    assert list(cluster.driver.signed_events) == [A.event_id()]


def test_evidence_is_still_kept_after_a_halt(cluster):
    cluster.driver.handle_message(cluster.certificate_message(A))
    cluster.driver.handle_message(cluster.certificate_message(B))
    assert cluster.driver.halted

    later = Transfer(PAYER, "bob", 1, 5)

    assert cluster.driver.record_evidence(signed(later))
    assert later.event_id() in cluster.driver.signed_events
    assert later.canonical() not in cluster.voted()
