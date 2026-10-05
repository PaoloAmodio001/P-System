from tests.signed_helpers import authorize, identity_with_claim, signed_transfer

from core.decision_status import DecisionStatus
from core.state import State
from network.node import Node


def test_byzantine_inconsistent_dissemination_cannot_create_unique_executable_state():
    """
    P15 Byzantine Safety:

    A Byzantine node may possess two valid, mutually conflicting signed
    alternatives and disseminate them inconsistently to honest peers.

    Honest nodes must:
      - preserve both events as canonical knowledge;
      - detect the resulting conflict;
      - never select the conflicting alternative as a winner;
      - never expose the resulting knowledge as UNIQUE;
      - keep their already-established local execution projection.
    """

    honest_a = Node(
        "p15-honest-A",
        State({"alice": 10}),
    )
    honest_b = Node(
        "p15-honest-B",
        State({"alice": 10}),
    )
    byzantine = Node(
        "p15-byzantine",
        State({"alice": 10}),
    )

    try:
        honest_a.start()
        honest_b.start()
        byzantine.start()

        identity, claim = identity_with_claim("alice")

        for node in (honest_a, honest_b, byzantine):
            authorize(node, claim)

        # Two valid signatures from the same identity and same nonce,
        # but mutually incompatible transfers.
        tx_a, signed_a = signed_transfer(
            identity,
            "alice",
            "bob",
            8,
            0,
        )

        tx_b, signed_b = signed_transfer(
            identity,
            "alice",
            "carol",
            8,
            0,
        )

        assert signed_a.verify()
        assert signed_b.verify()

        # Honest nodes initially observe different alternatives.
        assert honest_a.receive_signed(
            signed_a,
            broadcast=False,
        )

        assert honest_b.receive_signed(
            signed_b,
            broadcast=False,
        )

        assert honest_a.status() == DecisionStatus.UNIQUE
        assert honest_b.status() == DecisionStatus.UNIQUE

        # The Byzantine node knows both valid alternatives.
        byzantine.receive_signed(
            signed_a,
            broadcast=False,
        )
        byzantine.receive_signed(
            signed_b,
            broadcast=False,
        )

        # Simulate Byzantine inconsistent dissemination:
        # A receives only A, B receives only B.
        byzantine.signed_events = {
            signed_a.transfer.event_id(): signed_a,
        }
        byzantine.sync_with(honest_b)

        byzantine.signed_events = {
            signed_b.transfer.event_id(): signed_b,
        }
        byzantine.sync_with(honest_a)

        # Direct honest-to-honest reconciliation exposes the complete
        # conflicting knowledge.
        honest_a.sync_with(honest_b)
        honest_b.sync_with(honest_a)

        assert tx_a in honest_a.events
        assert tx_b in honest_a.events
        assert tx_a in honest_b.events
        assert tx_b in honest_b.events

        # The conflict must be explicit.
        assert honest_a.status() == DecisionStatus.CONFLICTED
        assert honest_b.status() == DecisionStatus.CONFLICTED

        # Neither conflicting alternative may become a newly selected
        # executable winner after reconciliation.
        assert honest_a.state.balance("bob") == 8
        assert honest_a.state.balance("carol") == 0

        assert honest_b.state.balance("bob") == 0
        assert honest_b.state.balance("carol") == 8

        # The Byzantine equivocation itself must be recorded.
        assert not byzantine.equivocations.is_empty()
        assert byzantine.equivocations.has_winner() is False

    finally:
        honest_a.stop()
        honest_b.stop()
        byzantine.stop()
