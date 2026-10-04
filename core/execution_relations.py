from dataclasses import dataclass

from core.event import Transfer
from core.dependency_graph import DependencyGraph
from core.execution_relation import (
    ExecutionRelation,
    classify_execution_relation,
)


@dataclass(frozen=True)
class ExecutionRelations:
    event_ids: tuple[str, ...] = ()
    causal: tuple[tuple[str, str], ...] = ()
    parallel: tuple[tuple[str, str], ...] = ()
    conflicts: tuple[tuple[str, str], ...] = ()

    def has_conflicts(self) -> bool:
        return bool(self.conflicts)


def build_execution_relations(
    events: list[Transfer],
) -> ExecutionRelations:

    causal = []
    parallel = []
    conflicts = []

    graph = DependencyGraph.build(events)

    for i, first in enumerate(events):
        for second in events[i + 1:]:
            relation = classify_execution_relation(
                first,
                second,
                events,
                graph,
            )

            pair = (
                first.event_id(),
                second.event_id(),
            )

            if relation == ExecutionRelation.CAUSAL:
                causal.append(pair)

            elif relation == ExecutionRelation.PARALLEL:
                parallel.append(pair)

            elif relation == ExecutionRelation.CONFLICT:
                conflicts.append(pair)

    return ExecutionRelations(
        event_ids=tuple(event.event_id() for event in events),
        causal=tuple(causal),
        parallel=tuple(parallel),
        conflicts=tuple(conflicts),
    )
