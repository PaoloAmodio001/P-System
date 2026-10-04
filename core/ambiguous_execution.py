from enum import Enum

from core.dependency_check import depends_on
from core.event import Transfer
from core.state_view import StateView


class ExecutionStatus(Enum):
    EXECUTABLE = "EXECUTABLE"
    BLOCKED = "BLOCKED"


def can_execute(
    view: StateView,
    event: Transfer,
    known_events: list[Transfer] | None = None,
) -> ExecutionStatus:

    if view.is_unique():
        return ExecutionStatus.EXECUTABLE

    if not view.is_ambiguous():
        return ExecutionStatus.BLOCKED

    alternatives = view.alternatives()

    if known_events is None:
        return ExecutionStatus.BLOCKED

    for alternative in alternatives:
        alternative_id = alternative.event_id()

        if event.event_id() == alternative_id:
            return ExecutionStatus.BLOCKED

        if depends_on(event, alternative_id, known_events):
            return ExecutionStatus.BLOCKED

    return ExecutionStatus.EXECUTABLE
