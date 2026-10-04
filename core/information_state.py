from enum import Enum

from core.conflict_state import ConflictState
from core.partial_knowledge import PartialKnowledge


class InformationStatus(Enum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    AMBIGUOUS = "AMBIGUOUS"


def classify_information(
    knowledge: PartialKnowledge,
    conflict: ConflictState | None = None,
) -> InformationStatus:

    if conflict is not None and conflict.is_conflicted():
        return InformationStatus.AMBIGUOUS

    if not knowledge.complete():
        return InformationStatus.INCOMPLETE

    return InformationStatus.COMPLETE
