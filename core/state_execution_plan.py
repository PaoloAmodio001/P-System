from dataclasses import dataclass

from core.event import Transfer, deduplicate_events
from core.state import State
from core.execution_index import ExecutionIndex
from core.parallel_execution import ParallelExecution
from core.state_relationship import (
    StateRelationship,
    classify_relationship,
)


@dataclass(frozen=True)
class StateExecutionPlan:
    ordered: tuple[tuple[str, str], ...]
    conflicts: tuple[tuple[str, str], ...]
    parallel_execution: ParallelExecution | None = None

    @property
    def parallel(self) -> tuple[tuple[str, str], ...]:
        if self.parallel_execution is None:
            return ()

        event_ids = self.parallel_execution.event_ids
        restricted = {
            tuple(sorted(pair))
            for pair in (*self.ordered, *self.conflicts)
        }

        return tuple(
            (first_id, second_id)
            for i, first_id in enumerate(event_ids)
            for second_id in event_ids[i + 1:]
            if tuple(sorted((first_id, second_id))) not in restricted
        )

    def has_conflicts(self) -> bool:
        return bool(self.conflicts)


def build_state_execution_plan(
    initial: State,
    events: list[Transfer],
) -> StateExecutionPlan:
    events = deduplicate_events(events)
    parallel = []
    ordered = []
    conflicts = []

    index = ExecutionIndex()
    index.add_all(events)

    checked_pairs: set[tuple[str, str]] = set()

    for first in events:
        first_id = first.event_id()

        for second in index.overlaps(first):
            second_id = second.event_id()

            pair = (first_id, second_id)
            normalized_pair = tuple(sorted(pair))

            if normalized_pair in checked_pairs:
                continue

            checked_pairs.add(normalized_pair)

            relationship = classify_relationship(
                initial,
                first,
                second,
            )

            if relationship == StateRelationship.COMPATIBLE:
                parallel.append(pair)

            elif relationship == StateRelationship.ORDER_DEPENDENT:
                ordered.append(pair)

            elif relationship == StateRelationship.CONFLICT:
                conflicts.append(pair)

    return StateExecutionPlan(
        ordered=tuple(ordered),
        conflicts=tuple(conflicts),
        parallel_execution=ParallelExecution(tuple(events)),
    )
