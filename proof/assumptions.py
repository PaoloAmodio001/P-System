"""Explicit assumptions that must accompany any final proof claim."""
from dataclasses import dataclass


@dataclass(frozen=True)
class SafetyAssumptions:
    cryptography_holds: bool = True
    hash_collision_resistance: bool = True
    trusted_initial_state: bool = True
    trusted_local_ingress: bool = True


@dataclass(frozen=True)
class LivenessAssumptions:
    eventual_message_delivery: bool = False
    fair_scheduling: bool = False
    honest_participation: bool = False


@dataclass(frozen=True)
class ByzantineModel:
    total_nodes: int
    byzantine_nodes: int
    authenticated_identities: bool = True
    arbitrary_message_mutation: bool = True
    arbitrary_message_order: bool = True

    @property
    def fault_fraction(self) -> float:
        if self.total_nodes <= 0:
            return 0.0
        return self.byzantine_nodes / self.total_nodes
