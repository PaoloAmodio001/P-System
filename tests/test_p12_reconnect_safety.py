from core.state import State
from network.node import Node
from network.reconciliation import reconcile
from tests.signed_helpers import identity_with_claim, signed_transfer


def test_reconciliation_does_not_bypass_authorization_gate():
    identity, claim = identity_with_claim("alice")
    transfer, signed = signed_transfer(
        identity,
        "alice",
        "bob",
        4,
        0,
    )

    node_a = Node(
        node_id="p12-a",
        initial_state=State({"alice": 4}),
        port=0,
    )

    node_b = Node(
        node_id="p12-b",
        initial_state=State({"alice": 4}),
        port=0,
    )

    # Signed evidence arrives before the identity claim.
    assert node_a.receive_signed(
        signed,
        broadcast=False,
    ) is False

    # The evidence is retained, but is not executable.
    assert signed in node_a.signed_events.values()
    assert transfer not in node_a.events
    assert node_a.state.balance("bob") == 0

    # Reconciliation must not convert pending evidence into execution.
    reconcile(node_a, node_b)

    assert transfer not in node_a.events
    assert transfer not in node_b.events
    assert node_a.state.balance("bob") == 0
    assert node_b.state.balance("bob") == 0


def test_identity_claim_promotes_pending_event_after_reconciliation():
    identity, claim = identity_with_claim("alice")
    transfer, signed = signed_transfer(
        identity,
        "alice",
        "bob",
        4,
        0,
    )

    node_a = Node(
        node_id="p12-a",
        initial_state=State({"alice": 4}),
        port=0,
    )

    node_b = Node(
        node_id="p12-b",
        initial_state=State({"alice": 4}),
        port=0,
    )

    # Event is authenticated but not yet authorized.
    assert node_a.receive_signed(
        signed,
        broadcast=False,
    ) is False

    reconcile(node_a, node_b)

    assert transfer not in node_a.events
    assert transfer not in node_b.events
    assert node_a.state.balance("bob") == 0
    assert node_b.state.balance("bob") == 0

    # Authorization is introduced explicitly.
    assert node_a.register_identity_claim(claim) is True

    assert node_a.state.balance("bob") == 4
    assert transfer in node_a.events


def test_reconciled_authorized_event_is_executable_without_reauthorization_bypass():
    identity, claim = identity_with_claim("alice")
    transfer, signed = signed_transfer(
        identity,
        "alice",
        "bob",
        4,
        0,
    )

    node_a = Node(
        node_id="p12-a",
        initial_state=State({"alice": 4}),
        port=0,
    )

    node_b = Node(
        node_id="p12-b",
        initial_state=State({"alice": 4}),
        port=0,
    )

    # Authorization exists before signed-event ingestion.
    assert node_a.register_identity_claim(claim) is True

    assert node_a.receive_signed(
        signed,
        broadcast=False,
    ) is True

    assert transfer in node_a.events
    assert node_a.state.balance("bob") == 4

    # Reconciliation transfers only already-authorized execution events.
    reconcile(node_a, node_b)

    assert transfer in node_b.events
    assert node_b.state.balance("bob") == 4
