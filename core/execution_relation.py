from enum import Enum

from core.dependency_check import depends_on
from core.dependency_graph import DependencyGraph
from core.event import Transfer
from core.incompatibility import incompatible


class ExecutionRelation(Enum):
    CAUSAL = "CAUSAL"
    PARALLEL = "PARALLEL"
    CONFLICT = "CONFLICT"


def classify_execution_relation(
    first: Transfer,
    second: Transfer,
    events: list[Transfer],
    graph: DependencyGraph | None = None,
) -> ExecutionRelation:

    first_id = first.event_id()
    second_id = second.event_id()

    # Una dipendenza causale ha priorità.
    if depends_on(second, first_id, events, graph):
        return ExecutionRelation.CAUSAL

    if depends_on(first, second_id, events, graph):
        return ExecutionRelation.CAUSAL

    # Conflitto reale: stesso sender + stesso nonce,
    # ma eventi differenti.
    if incompatible(first, second):
        return ExecutionRelation.CONFLICT

    # Nessuna dipendenza e nessun conflitto.
    return ExecutionRelation.PARALLEL
