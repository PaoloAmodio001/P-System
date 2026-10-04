from enum import Enum

from core.conflict_state import ConflictState
from core.uncertainty_boundary import UncertaintyBoundary


class DecisionStatus(Enum):
    UNIQUE = "UNIQUE"
    UNCERTAIN = "UNCERTAIN"
    CONFLICTED = "CONFLICTED"


def classify_decision(
    boundary: UncertaintyBoundary,
    conflict: ConflictState | None = None,
) -> DecisionStatus:

    if conflict is not None and conflict.is_conflicted():
        return DecisionStatus.CONFLICTED

    if boundary.potentially_relevant:
        return DecisionStatus.UNCERTAIN

    return DecisionStatus.UNIQUE
