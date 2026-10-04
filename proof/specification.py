"""Machine-readable system scope and proof assumptions."""
from dataclasses import dataclass
from enum import Enum


class ProofStatus(str, Enum):
    PROVEN = "PROVEN"
    EXHAUSTIVELY_CHECKED = "EXHAUSTIVELY_CHECKED"
    PROPERTY_TESTED = "PROPERTY_TESTED"
    EMPIRICALLY_SUPPORTED = "EMPIRICALLY_SUPPORTED"
    NOT_PROVEN = "NOT_PROVEN"
    FAILED = "FAILED"


@dataclass(frozen=True)
class SystemAssumptions:
    trusted_local_ingress: bool = True
    signed_network_ingress_required: bool = True
    authenticated_identity_required_for_execution: bool = True
    reliable_event_id_hash: bool = True
    cryptographic_signature_unforgeability: bool = True
    eventual_delivery: bool = False
    bounded_faults: int | None = None


@dataclass(frozen=True)
class ProofObligation:
    identifier: str
    title: str
    statement: str
    status: ProofStatus = ProofStatus.NOT_PROVEN
    assumptions: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()


DEFAULT_OBLIGATIONS = (
    ProofObligation("P01", "Invalid transfers never execute", "A rejected transfer never changes operational state."),
    ProofObligation("P02", "Causal dependencies are preserved", "An executable event requires every declared parent to be executable."),
    ProofObligation("P03", "Conflicts do not execute together", "Conflicting alternatives cannot both be selected into one projection."),
    ProofObligation("P04", "Independent events remain independently executable", "Non-conflicting, causally complete events may coexist."),
    ProofObligation("P05", "Hidden relevant knowledge blocks uniqueness", "A relevant undiscovered extension can invalidate a unique decision."),
    ProofObligation("P06", "Irrelevant extension preserves decision", "Adding an irrelevant event does not change the decision."),
    ProofObligation("P07", "Signed event authenticity", "A modified payload or signature is rejected."),
    ProofObligation("P08", "Identity binding", "A signed event executes only when bound to a valid identity claim."),
    ProofObligation("P09", "Multi-node convergence", "Nodes with equivalent authorized knowledge converge to the same projection."),
    ProofObligation("P10", "Duplicate idempotence", "Repeating the same event does not duplicate execution."),
    ProofObligation("P11", "Replay protection", "Replayed signed evidence cannot cause duplicate execution."),
    ProofObligation("P12", "Reconnect safety", "Reconnect/reconciliation never bypasses authorization gates."),
    ProofObligation("P13", "Concurrency safety", "Concurrent ingress preserves state invariants."),
    ProofObligation("P14", "Transport security scope", "Network confidentiality/integrity properties are explicitly modeled."),
    ProofObligation("P15", "Byzantine tolerance", "The claimed fault model is explicitly stated and proven if claimed."),
    ProofObligation("P16", "Liveness", "Eventual progress holds only under explicit network/liveness assumptions."),
)
