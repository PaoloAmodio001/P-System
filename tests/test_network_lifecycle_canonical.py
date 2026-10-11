from core.event import Transfer
from core.state import State
from core.signed_event import SignedTransfer
from core.event_lifecycle import EventLifecycle
from network.node import Node
from tests.signed_helpers import identity_with_claim


def test_reordered_parents_keep_executed_lifecycle(request):
    identity, claim = identity_with_claim("alice")
    node = Node(
        node_id="lifecycle-canonical-test",
        initial_state=State({"alice": 3}),
        port=0,
    )

    request.addfinalizer(node.stop)
    assert node.register_identity_claim(claim)

    parent_a = Transfer("alice", "x", 1, 0)
    parent_b = Transfer(
        "alice", "y", 1, 1, (parent_a.event_id(),)
    )
    assert node.receive(parent_a)
    assert node.receive(parent_b)

    parents = (parent_a.event_id(), parent_b.event_id())
    transfer = Transfer("alice", "bob", 1, 2, parents)
    reordered = Transfer(
        "alice", "bob", 1, 2, tuple(reversed(parents))
    )

    assert transfer.event_id() == reordered.event_id()
    assert transfer != reordered

    signed = SignedTransfer.create(identity, transfer)
    assert node.receive_signed(signed, broadcast=False)

    signed_reordered = SignedTransfer.create(identity, reordered)
    assert node.signed_event_lifecycle(signed_reordered) == EventLifecycle.EXECUTED
