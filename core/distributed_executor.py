from dataclasses import dataclass

from core.ambiguous_execution import ExecutionStatus, can_execute
from core.dependency_graph import DependencyGraph
from core.event import Transfer
from core.execution_plan import ExecutionPlan
from core.proof import apply_transfer
from core.state import State
from core.state_view import StateView


@dataclass(frozen=True)
class ExecutionResult:
    node_id: str
    state: State
    completed: frozenset[str]
    blocked: frozenset[str] = frozenset()

    @property
    def state_root(self) -> str:
        return self.state.root()


@dataclass(frozen=True)
class ClassificationResult:
    executable: tuple[str, ...]
    blocked: tuple[str, ...]


class DistributedExecutor:
    def __init__(self, node_id: str):
        self.node_id = node_id

    def decide_execution(
        self,
        events: list[Transfer],
    ):
        from core.execution_decision import decide

        relations = self.classify_relations(
            events,
        )

        return decide(
            relations,
        )

    def classify_relations(
        self,
        events: list[Transfer],
    ):
        from core.execution_relations import build_execution_relations

        return build_execution_relations(
            events,
        )

    def classify_relation(
        self,
        first: Transfer,
        second: Transfer,
        events: list[Transfer],
    ):
        from core.execution_relation import classify_execution_relation

        return classify_execution_relation(
            first,
            second,
            events,
        )

    def plan_state(
        self,
        initial: State,
        events: list[Transfer],
    ):
        from core.state_execution_plan import build_state_execution_plan

        return build_state_execution_plan(
            initial,
            events,
        )

    def classify(
        self,
        view: StateView,
        events: list[Transfer],
    ) -> ClassificationResult:
        executable = []
        blocked = []

        for event in events:
            status = can_execute(
                view,
                event,
                events,
            )

            if status == ExecutionStatus.EXECUTABLE:
                executable.append(event.event_id())
            else:
                blocked.append(event.event_id())

        return ClassificationResult(
            executable=tuple(sorted(executable)),
            blocked=tuple(sorted(blocked)),
        )

    def _execute_events(
        self,
        initial: State,
        events: list[Transfer],
    ) -> tuple[State, frozenset[str]]:
        state = initial.copy()
        event_map = {
            event.event_id(): event
            for event in events
        }

        graph = DependencyGraph.build(events)

        if graph.has_cycle():
            raise ValueError("CYCLIC DEPENDENCY")

        completed: set[str] = set()

        while len(completed) < len(events):
            ready = graph.ready(completed)

            if not ready:
                raise ValueError("NO READY EVENTS")

            for event_id in sorted(ready):
                event = event_map[event_id]
                state = apply_transfer(state, event)
                completed.add(event_id)

        return state, frozenset(completed)

    def execute(
        self,
        initial: State,
        events: list[Transfer],
        plan: ExecutionPlan,
    ) -> ExecutionResult:
        if plan.has_conflicts():
            raise ValueError("CANNOT EXECUTE CONFLICTING PLAN")

        state, completed = self._execute_events(
            initial,
            events,
        )

        return ExecutionResult(
            node_id=self.node_id,
            state=state,
            completed=completed,
        )


    def execute_view(
        self,
        initial: State,
        view: StateView,
        events: list[Transfer],
    ) -> ExecutionResult:
        classification = self.classify(
            view,
            events,
        )

        executable_ids = set(classification.executable)
        blocked_ids = set(classification.blocked)

        # Il planning globale identifica le alternative
        # conflittuali senza scegliere un vincitore.
        decision = self.decide_execution(events)


        for first_id, second_id in decision.conflicts:
            executable_ids.discard(first_id)
            executable_ids.discard(second_id)
            blocked_ids.add(first_id)
            blocked_ids.add(second_id)

        # Un evento bloccato rende non eseguibili
        # anche tutti i suoi discendenti causali.
        from core.block_propagation import propagate_blocked

        blocked_ids = propagate_blocked(
            events,
            blocked_ids,
        )

        executable_ids.difference_update(
            blocked_ids
        )

        event_map = {
            event.event_id(): event
            for event in events
        }

        executable_events = [
            event
            for event in events
            if event.event_id() in executable_ids
        ]

        if not executable_events:
            return ExecutionResult(
                node_id=self.node_id,
                state=initial.copy(),
                completed=frozenset(),
                blocked=frozenset(blocked_ids),
            )

        state, completed = self._execute_events(
            initial,
            executable_events,
        )

        return ExecutionResult(
            node_id=self.node_id,
            state=state,
            completed=completed,
            blocked=frozenset(blocked_ids),
        )
