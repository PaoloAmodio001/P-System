from concurrent.futures import ThreadPoolExecutor

from core.state import State
from network.node import Node
from tests.signed_helpers import identity_with_claim, signed_transfer


def test_p13_concurrent_distinct_events_both_execute():
    identity_a, claim_a = identity_with_claim("alice")
    identity_c, claim_c = identity_with_claim("carol")

    transfer_a, signed_a = signed_transfer(identity_a, "alice", "bob", 2, 0)
    transfer_c, signed_c = signed_transfer(identity_c, "carol", "dave", 3, 0)

    node = Node(
        "p13-distinct",
        State({"alice": 2, "carol": 3}),
        port=0,
    )

    try:
        assert node.register_identity_claim(claim_a)
        assert node.register_identity_claim(claim_c)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(
                    lambda event: node.receive_signed(event, broadcast=False),
                    (signed_a, signed_c),
                )
            )

        assert sum(bool(result) for result in results) == 2
        assert transfer_a in node.events
        assert transfer_c in node.events
        assert transfer_a in node.local_events
        assert transfer_c in node.local_events
        assert node.state.balance("alice") == 0
        assert node.state.balance("bob") == 2
        assert node.state.balance("carol") == 0
        assert node.state.balance("dave") == 3
    finally:
        node.stop()
