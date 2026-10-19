from dataclasses import dataclass

from core.event import Transfer, deduplicate_events
from core.incompatibility import incompatible
from core.commutativity import commute
from core.execution_index import ExecutionIndex
from core.parallel_execution import ParallelExecution
from core.state import State


@dataclass(frozen=True)
class ExecutionRelation:
    first: str
    second: str
    relation: str


@dataclass(frozen=True)
class ExecutionPlan:
    ordered: tuple[tuple[str, str], ...]
    conflicts: tuple[tuple[str, str], ...]
    parallel_execution: ParallelExecution | None = None

    @property
    def parallel(self) -> tuple[tuple[str, str], ...]:
        if self.parallel_execution is None:
            return ()

        event_ids = self.parallel_execution.event_ids
        restricted = set(self.ordered) | set(self.conflicts)

        return tuple(
            (first_id, second_id)
            for i, first_id in enumerate(event_ids)
            for second_id in event_ids[i + 1:]
            if tuple(sorted((first_id, second_id))) not in restricted
        )

    def has_conflicts(self) -> bool:
        return bool(self.conflicts)

    @property
    def parallel_event_count(self) -> int:
        if self.parallel_execution is None:
            return 0
        return len(self.parallel_execution.event_ids)


def build_execution_plan(
    initial: State,
    events: list[Transfer],
) -> ExecutionPlan:

    events = deduplicate_events(events)
    ordered = []
    conflicts = []

    index = ExecutionIndex()
    index.add_all(events)

    event_by_id = {event.event_id(): event for event in events}

    checked_pairs: set[tuple[str, str]] = set()

    for first in events:
        first_id = first.event_id()

        overlapping = index.overlaps(first)

        for second in overlapping:
            second_id = second.event_id()

            pair = tuple(sorted((first_id, second_id)))

            if pair in checked_pairs:
                continue

            checked_pairs.add(pair)

            # Intrinsic conflict:
            # same sender + same nonce + different event.
            if incompatible(first, second):
                conflicts.append(pair)
                continue

            # If they genuinely commute, they can be executed
            # independently.
            if commute(initial, first, second):
                continue

            # Otherwise the pair has an execution dependency.
            ordered.append(pair)

    return ExecutionPlan(
        ordered=tuple(ordered),
        conflicts=tuple(conflicts),
        parallel_execution=ParallelExecution(tuple(events)),
    )
