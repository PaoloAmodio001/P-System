from dataclasses import dataclass
from enum import Enum

from core.partial_knowledge import PartialKnowledge


class CompletenessStatus(Enum):
    UNKNOWN = "UNKNOWN"
    COMPLETE = "COMPLETE"


@dataclass(frozen=True)
class CompletenessProof:
    known_event_ids: frozenset[str]
    frontier: frozenset[str]

    def verify(self, knowledge: PartialKnowledge) -> bool:
        if self.known_event_ids != knowledge.event_ids():
            return False

        if knowledge.missing_parents():
            return False

        return True


def prove_completeness(
    knowledge: PartialKnowledge,
    frontier: frozenset[str],
) -> CompletenessProof | None:

    if not knowledge.complete():
        return None

    return CompletenessProof(
        known_event_ids=knowledge.event_ids(),
        frontier=frontier,
    )
