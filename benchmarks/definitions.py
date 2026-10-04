"""Benchmark workload definitions without executing them."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Benchmark:
    name: str
    description: str
    target: str


BENCHMARKS = (
    Benchmark("event_ingestion", "Trusted Transfer ingestion and projection rebuild", "Node.receive"),
    Benchmark("signed_ingestion", "Authenticated/authorized signed-event ingestion", "Node.receive_signed"),
    Benchmark("identity_verification", "Identity claim verification and promotion", "IdentityClaim.verify"),
    Benchmark("projection_rebuild", "Local executable projection reconstruction", "Node._rebuild_local_projection"),
    Benchmark("conflict_detection", "Conflict discovery under competing events", "ConflictResolver"),
    Benchmark("decision", "Decision-context construction", "Node.decision_context"),
    Benchmark("reconciliation", "Signed knowledge reconciliation", "Node.sync_with"),
    Benchmark("convergence", "Multi-node convergence workloads", "proof.convergence"),
    Benchmark("model_check", "Finite state-space exploration", "proof.model_checker"),
)
