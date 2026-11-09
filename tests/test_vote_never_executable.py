"""An honest node votes for no event that no state can run.

A zero amount or a transfer to its own sender is well formed, and the model refuses it only at
execution. Before this rule a node voted for it, so a certificate could form, run nothing, and hold
the nonce of its sender for good: every later event of that sender waited on it. Now `auth` refuses it,
and the model holds for any `auth`.
"""

import pytest

from core.attestation import Committee, can_ever_execute
from core.event import Transfer
from core.signed_event import SignedTransfer
from core.state import State
from crypto.identity import Identity
from network.quorum import QuorumConfig, QuorumRuntime

SENDER = Identity.create()
ALICE = SENDER.identity_id
MEMBERS = sorted((Identity.create() for _ in range(4)), key=lambda m: m.public_key)
GENESIS = State({ALICE: 100})
COMMITTEE = Committee.create([m.public_key for m in MEMBERS], 1, GENESIS)


@pytest.fixture
def runtime(tmp_path):
    made = QuorumRuntime(QuorumConfig(COMMITTEE, MEMBERS[0], tmp_path / "v.sqlite", create=True), GENESIS)
    yield made
    made.close()


@pytest.mark.parametrize(
    "event",
    [Transfer(ALICE, "bob", 0, 0), Transfer(ALICE, ALICE, 5, 0)],
    ids=["zero amount", "to self"],
)
def test_no_vote_for_what_can_never_run(runtime, event):
    signed = SignedTransfer.create(SENDER, event)
    output = runtime.submit_group([signed])

    assert output.broadcasts == ()
    assert runtime.replica.votes() == []
    # The nonce is still free for a real event.
    real = SignedTransfer.create(SENDER, Transfer(ALICE, "bob", 5, 0))
    assert runtime.submit_group([real]).broadcasts
    assert runtime.replica.votes() == [real.transfer]


def test_a_request_from_a_peer_gets_no_vote_either(runtime):
    from network.message import encode_vote_request

    signed = SignedTransfer.create(SENDER, Transfer(ALICE, "bob", 0, 0))
    output, error = runtime.handle_group([encode_vote_request(signed)])

    assert error is None and output.replies == ()
    assert runtime.replica.votes() == []


def test_the_rule():
    assert can_ever_execute(Transfer(ALICE, "bob", 1, 0))
    assert not can_ever_execute(Transfer(ALICE, "bob", 0, 0))
    assert not can_ever_execute(Transfer(ALICE, ALICE, 1, 0))
