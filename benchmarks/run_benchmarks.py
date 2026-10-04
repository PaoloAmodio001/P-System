"""Deterministic microbenchmark entry point.

Benchmarks are intentionally local and bounded; network timing is not treated
as a correctness proof. Results are serialized for later comparison.
"""
from pathlib import Path
from benchmarks.runner import run_callable
from benchmarks.report import write_json
from core.event import Transfer
from core.state import State
from core.identity_claim import IdentityClaim
from core.signed_event import SignedTransfer
from crypto.identity import Identity
from network.node import Node


def build_workloads():
    identity = Identity.create()
    claim = IdentityClaim.create(identity, "alice")
    signed = SignedTransfer.create(identity, Transfer("alice", "bob", 1, 0))

    node_receive = Node("bench-receive", State({"alice": 100000}))
    node_receive.receive(Transfer("alice", "bob", 1, 0), broadcast=False)

    node_signed = Node("bench-signed", State({"alice": 100000}))
    node_signed.register_identity_claim(claim)

    def decision():
        node_receive.status()

    def identity_verify():
        claim.verify()

    def projection():
        node_receive._rebuild_local_projection()

    def signed_ingestion():
        # Rebuild a fresh node each iteration so the workload measures the
        # complete authorization/execution path rather than duplicate reject.
        n = Node("bench-signed-iteration", State({"alice": 1}))
        n.register_identity_claim(claim)
        n.receive_signed(signed, broadcast=False)

    return (
        run_callable("decision", decision, 1000),
        run_callable("identity_verification", identity_verify, 5000),
        run_callable("projection_rebuild", projection, 1000),
        run_callable("signed_ingestion", signed_ingestion, 250),
    )


def main() -> int:
    results = build_workloads()
    out = Path("audit-reports")
    out.mkdir(parents=True, exist_ok=True)
    write_json(results, out / "benchmark-results.json")
    for result in results:
        rate = result.iterations / result.elapsed_seconds if result.elapsed_seconds else 0.0
        print(f"{result.name}: {result.iterations} iterations, {result.elapsed_seconds:.6f}s, {rate:.2f} ops/s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
