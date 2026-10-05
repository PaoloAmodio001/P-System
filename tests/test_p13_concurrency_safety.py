from concurrent.futures import ThreadPoolExecutor

from core.state import State
from network.node import Node
from tests.signed_helpers import identity_with_claim, signed_transfer


def _run_concurrent_ingress(node, signed, workers, attempts):
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(
            pool.map(
                lambda _: node.receive_signed(
                    signed,
                    broadcast=False,
                ),
                range(attempts),
            )
        )


def test_concurrent_duplicate_signed_ingress_executes_exactly_once():
    identity, claim = identity_with_claim("alice")
    transfer, signed = signed_transfer(
        identity,
        "alice",
        "bob",
        3,
        0,
    )

    node = Node(
        node_id="p13-single",
        initial_state=State({"alice": 3}),
        port=0,
    )

    assert node.register_identity_claim(claim)

    results = _run_concurrent_ingress(
        node,
        signed,
        workers=8,
        attempts=32,
    )

    assert sum(bool(result) for result in results) == 1
    assert node.state.balance("alice") == 0
    assert node.state.balance("bob") == 3
    assert node.state.nonce("alice") == 1
    assert len(node.local_events) == 1
    assert transfer in node.events


def test_concurrent_duplicate_ingress_is_stable_across_repeated_rounds():
    for round_number in range(10):
        identity, claim = identity_with_claim(
            f"alice-{round_number}"
        )

        transfer, signed = signed_transfer(
            identity,
            f"alice-{round_number}",
            f"bob-{round_number}",
            1,
            0,
        )

        node = Node(
            node_id=f"p13-round-{round_number}",
            initial_state=State({
                f"alice-{round_number}": 1,
            }),
            port=0,
        )

        assert node.register_identity_claim(claim)

        results = _run_concurrent_ingress(
            node,
            signed,
            workers=16,
            attempts=64,
        )

        assert sum(bool(result) for result in results) == 1
        assert len(node.local_events) == 1
        assert transfer in node.events
        assert (
            node.state.balance(f"bob-{round_number}") == 1
        )


def test_concurrent_ingress_does_not_duplicate_received_evidence():
    identity, claim = identity_with_claim("alice")
    transfer, signed = signed_transfer(
        identity,
        "alice",
        "bob",
        2,
        0,
    )

    node = Node(
        node_id="p13-received",
        initial_state=State({"alice": 2}),
        port=0,
    )

    assert node.register_identity_claim(claim)

    results = _run_concurrent_ingress(
        node,
        signed,
        workers=32,
        attempts=128,
    )

    assert sum(bool(result) for result in results) == 1
    assert len(node.local_events) == 1
    assert len(node.received) == 1
    assert node.received[0] == signed
    assert transfer in node.events
