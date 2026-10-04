from core.ambiguous_execution import ExecutionStatus, can_execute
from core.conflict_state import ConflictState
from core.event import Transfer
from core.state import State
from core.state_view import StateView


def test_executor_can_separate_executable_and_blocked_events():
    conflict_a = Transfer(
        "alice",
        "bob",
        6,
        0,
    )

    conflict_b = Transfer(
        "alice",
        "carol",
        7,
        0,
    )

    blocked = Transfer(
        "bob",
        "dave",
        2,
        0,
        parents=(conflict_a.event_id(),),
    )

    independent = Transfer(
        "frank",
        "gina",
        2,
        0,
    )

    view = StateView.ambiguous(
        ConflictState(
            alternatives=(conflict_a, conflict_b)
        )
    )

    events = [
        conflict_a,
        conflict_b,
        blocked,
        independent,
    ]

    assert can_execute(
        view,
        blocked,
        events,
    ) == ExecutionStatus.BLOCKED

    assert can_execute(
        view,
        independent,
        events,
    ) == ExecutionStatus.EXECUTABLE


def test_unique_state_allows_normal_execution():
    state = State(
        balances={
            "alice": 10,
            "bob": 0,
        }
    )

    view = StateView.unique(state)

    event = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    assert can_execute(
        view,
        event,
        [event],
    ) == ExecutionStatus.EXECUTABLE


def test_distributed_executor_classifies_events():
    from core.distributed_executor import DistributedExecutor

    conflict_a = Transfer(
        "alice",
        "bob",
        6,
        0,
    )

    conflict_b = Transfer(
        "alice",
        "carol",
        7,
        0,
    )

    blocked = Transfer(
        "bob",
        "dave",
        2,
        0,
        parents=(conflict_a.event_id(),),
    )

    independent = Transfer(
        "frank",
        "gina",
        2,
        0,
    )

    view = StateView.ambiguous(
        ConflictState(
            alternatives=(conflict_a, conflict_b)
        )
    )

    events = [
        conflict_a,
        conflict_b,
        blocked,
        independent,
    ]

    executor = DistributedExecutor("node-1")

    result = executor.classify(
        view,
        events,
    )

    assert independent.event_id() in result.executable
    assert blocked.event_id() in result.blocked

    assert conflict_a.event_id() in result.blocked
    assert conflict_b.event_id() in result.blocked


def test_execution_result_preserves_blocked_events():
    from core.distributed_executor import ExecutionResult

    state = State(
        balances={
            "alice": 10,
            "bob": 0,
        }
    )

    blocked_id = Transfer(
        "alice",
        "bob",
        5,
        0,
    ).event_id()

    result = ExecutionResult(
        node_id="node-1",
        state=state,
        completed=frozenset(),
        blocked=frozenset({blocked_id}),
    )

    assert blocked_id in result.blocked
    assert result.completed == frozenset()
    assert result.state.root() == state.root()


def test_execute_view_runs_independent_events_and_preserves_blocked():
    from core.distributed_executor import DistributedExecutor

    initial = State(
        balances={
            "alice": 10,
            "bob": 0,
            "frank": 5,
            "gina": 0,
        }
    )

    conflict_a = Transfer(
        "alice",
        "bob",
        6,
        0,
    )

    conflict_b = Transfer(
        "alice",
        "bob",
        7,
        0,
    )

    blocked = Transfer(
        "bob",
        "dave",
        2,
        0,
        parents=(conflict_a.event_id(),),
    )

    independent = Transfer(
        "frank",
        "gina",
        2,
        0,
    )

    view = StateView.ambiguous(
        ConflictState(
            alternatives=(conflict_a, conflict_b)
        )
    )

    events = [
        conflict_a,
        conflict_b,
        blocked,
        independent,
    ]

    executor = DistributedExecutor("node-1")

    result = executor.execute_view(
        initial,
        view,
        events,
    )

    assert independent.event_id() in result.completed
    assert independent.event_id() not in result.blocked

    assert conflict_a.event_id() in result.blocked
    assert conflict_b.event_id() in result.blocked
    assert blocked.event_id() in result.blocked

    assert result.state.balance("frank") == 3
    assert result.state.balance("gina") == 2

    assert result.state.balance("alice") == 10
    assert result.state.balance("bob") == 0


def test_executor_runs_compatible_work_while_conflict_is_blocked():
    from core.distributed_executor import DistributedExecutor
    from core.state_execution_plan import build_state_execution_plan

    initial = State(
        balances={
            "alice": 10,
            "bob": 0,
            "carol": 5,
            "dave": 0,
        }
    )

    compatible_a = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    compatible_b = Transfer(
        "carol",
        "dave",
        2,
        0,
    )

    conflict_a = Transfer(
        "alice",
        "bob",
        10,
        1,
    )

    conflict_b = Transfer(
        "alice",
        "dave",
        9,
        1,
    )

    events = [
        compatible_a,
        compatible_b,
        conflict_a,
        conflict_b,
    ]

    plan = build_state_execution_plan(
        initial,
        events,
    )

    assert plan.has_conflicts()

    executor = DistributedExecutor("node-1")

    # Il test verifica il requisito architetturale:
    # il lavoro compatibile deve poter continuare
    # mentre il conflitto rimane sospeso.
    view = StateView.unique(initial)

    result = executor.execute_view(
        initial,
        view,
        [
            compatible_a,
            compatible_b,
        ],
    )

    assert compatible_a.event_id() in result.completed
    assert compatible_b.event_id() in result.completed

    assert result.state.balance("alice") == 7
    assert result.state.balance("bob") == 3
    assert result.state.balance("carol") == 3
    assert result.state.balance("dave") == 2


def test_executor_plan_state_uses_state_relationships():
    from core.distributed_executor import DistributedExecutor

    initial = State(
        balances={
            "alice": 10,
            "bob": 0,
            "carol": 5,
            "dave": 0,
        }
    )

    compatible_a = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    compatible_b = Transfer(
        "carol",
        "dave",
        2,
        0,
    )

    executor = DistributedExecutor("node-1")

    plan = executor.plan_state(
        initial,
        [
            compatible_a,
            compatible_b,
        ],
    )

    pair = (
        compatible_a.event_id(),
        compatible_b.event_id(),
    )

    assert pair in plan.parallel
    assert plan.ordered == ()
    assert plan.conflicts == ()
    assert not plan.has_conflicts()


def test_executor_mixed_independent_dependent_and_conflict():
    from core.distributed_executor import DistributedExecutor
    from core.state_execution_plan import build_state_execution_plan

    initial = State(
        balances={
            "alice": 10,
            "bob": 0,
            "carol": 5,
            "dave": 0,
        }
    )

    # Catena causale: alice -> bob
    first = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    # Dipende causalmente da "first"
    second = Transfer(
        "bob",
        "carol",
        2,
        0,
        parents=(first.event_id(),),
    )

    # Completamente indipendente
    independent = Transfer(
        "carol",
        "dave",
        1,
        0,
    )

    # Alternativa conflittuale con "first":
    # stesso sender + stesso nonce, ma operazione diversa.
    conflict = Transfer(
        "alice",
        "carol",
        4,
        0,
    )

    events = [
        first,
        second,
        independent,
        conflict,
    ]

    plan = build_state_execution_plan(
        initial,
        events,
    )

    assert plan.has_conflicts()

    executor = DistributedExecutor("node-1")

    # Per questa fase testiamo soltanto il ramo
    # non ambiguo: la catena causale + evento indipendente.
    result = executor.execute_view(
        initial,
        StateView.unique(initial),
        [
            first,
            second,
            independent,
        ],
    )

    assert first.event_id() in result.completed
    assert second.event_id() in result.completed
    assert independent.event_id() in result.completed

    assert result.state.balance("alice") == 7
    assert result.state.balance("bob") == 1
    assert result.state.balance("carol") == 6
    assert result.state.balance("dave") == 1

    # L'alternativa conflittuale non deve essere
    # selezionata automaticamente.
    assert conflict.event_id() not in result.completed


def test_executor_preserves_conflict_without_selecting_winner():
    from core.distributed_executor import DistributedExecutor
    from core.conflict_state import ConflictState

    initial = State(
        balances={
            "alice": 10,
            "bob": 0,
            "carol": 0,
        }
    )

    first = Transfer(
        "alice",
        "bob",
        4,
        0,
    )

    alternative = Transfer(
        "alice",
        "carol",
        6,
        0,
    )

    conflict = ConflictState(
        alternatives=(first, alternative)
    )

    view = StateView.ambiguous(conflict)

    executor = DistributedExecutor("node-1")

    result = executor.execute_view(
        initial,
        view,
        [first, alternative],
    )

    assert result.completed == frozenset()

    assert first.event_id() not in result.completed
    assert alternative.event_id() not in result.completed

    assert result.state.root() == initial.root()

    assert result.blocked == frozenset({
        first.event_id(),
        alternative.event_id(),
    })


def test_executor_classify_relation_causal():
    from core.distributed_executor import DistributedExecutor
    from core.execution_relation import ExecutionRelation

    first = Transfer("alice", "bob", 3, 0)

    second = Transfer(
        "bob",
        "carol",
        2,
        0,
        parents=(first.event_id(),),
    )

    executor = DistributedExecutor("node-1")

    assert executor.classify_relation(
        first,
        second,
        [first, second],
    ) == ExecutionRelation.CAUSAL


def test_executor_classify_relation_parallel():
    from core.distributed_executor import DistributedExecutor
    from core.execution_relation import ExecutionRelation

    first = Transfer("alice", "bob", 3, 0)
    second = Transfer("carol", "dave", 2, 0)

    executor = DistributedExecutor("node-1")

    assert executor.classify_relation(
        first,
        second,
        [first, second],
    ) == ExecutionRelation.PARALLEL


def test_executor_classify_relation_conflict():
    from core.distributed_executor import DistributedExecutor
    from core.execution_relation import ExecutionRelation

    first = Transfer("alice", "bob", 3, 0)
    second = Transfer("alice", "carol", 4, 0)

    executor = DistributedExecutor("node-1")

    assert executor.classify_relation(
        first,
        second,
        [first, second],
    ) == ExecutionRelation.CONFLICT


def test_execution_decision_blocks_only_conflicting_events():
    from core.distributed_executor import DistributedExecutor

    initial = State(
        balances={
            "alice": 10,
            "bob": 0,
            "carol": 5,
            "dave": 0,
        }
    )

    first = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    independent = Transfer(
        "carol",
        "dave",
        2,
        0,
    )

    conflict = Transfer(
        "alice",
        "carol",
        4,
        0,
    )

    executor = DistributedExecutor("node-1")

    decision = executor.decide_execution(
        [
            first,
            independent,
            conflict,
        ]
    )

    # Le due alternative conflittuali devono rimanere entrambe bloccate.
    # Nessuna delle due può diventare implicitamente il vincitore.
    assert first.event_id() not in decision.executable
    assert conflict.event_id() not in decision.executable

    # L'evento indipendente può invece continuare.
    assert independent.event_id() in decision.executable

    assert decision.has_conflicts()


def test_execute_view_filters_conflicting_alternatives():
    from core.distributed_executor import DistributedExecutor

    initial = State(
        balances={
            "alice": 10,
            "bob": 0,
            "carol": 5,
            "dave": 0,
        }
    )

    first = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    conflict = Transfer(
        "alice",
        "carol",
        4,
        0,
    )

    independent = Transfer(
        "carol",
        "dave",
        2,
        0,
    )

    executor = DistributedExecutor("node-1")

    result = executor.execute_view(
        initial,
        StateView.unique(initial),
        [
            first,
            conflict,
            independent,
        ],
    )

    assert first.event_id() not in result.completed
    assert conflict.event_id() not in result.completed

    assert independent.event_id() in result.completed

    assert result.blocked == frozenset({
        first.event_id(),
        conflict.event_id(),
    })

    assert result.state.balance("alice") == 10
    assert result.state.balance("bob") == 0
    assert result.state.balance("carol") == 3
    assert result.state.balance("dave") == 2


def test_full_execution_pipeline_combined_relations():
    from core.distributed_executor import DistributedExecutor

    initial = State(
        balances={
            "alice": 10,
            "bob": 0,
            "carol": 5,
            "dave": 0,
        }
    )

    first = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    second = Transfer(
        "bob",
        "carol",
        2,
        0,
        parents=(first.event_id(),),
    )

    independent = Transfer(
        "carol",
        "dave",
        1,
        0,
    )

    conflict = Transfer(
        "alice",
        "carol",
        4,
        0,
    )

    events = [
        first,
        second,
        independent,
        conflict,
    ]

    executor = DistributedExecutor("node-1")

    decision = executor.decide_execution(events)

    # Le alternative conflittuali non sono eseguibili.
    assert conflict.event_id() not in decision.executable

    # La prima alternativa coinvolta nel conflitto non deve
    # diventare automaticamente il vincitore.
    assert first.event_id() not in decision.executable

    # L'esecuzione reale deve quindi ricevere soltanto il
    # ramo non ambiguo.
    result = executor.execute_view(
        initial,
        StateView.unique(initial),
        [
            first,
            second,
            independent,
            conflict,
        ],
    )

    assert first.event_id() not in result.completed
    assert second.event_id() not in result.completed
    assert independent.event_id() in result.completed

    assert result.blocked == frozenset({
        first.event_id(),
        second.event_id(),
        conflict.event_id(),
    })

    # Solo l'evento indipendente modifica lo stato.
    assert result.state.balance("alice") == 10
    assert result.state.balance("bob") == 0
    assert result.state.balance("carol") == 4
    assert result.state.balance("dave") == 1


def test_conflict_does_not_block_independent_causal_branch():
    from core.distributed_executor import DistributedExecutor

    initial = State(
        balances={
            "alice": 10,
            "bob": 0,
            "carol": 10,
            "dave": 0,
            "eve": 0,
        }
    )

    # RAMO A: contiene un conflitto.
    branch_a_first = Transfer(
        "alice",
        "bob",
        3,
        0,
    )

    branch_a_conflict = Transfer(
        "alice",
        "dave",
        4,
        0,
    )

    branch_a_child = Transfer(
        "bob",
        "eve",
        1,
        0,
        parents=(branch_a_first.event_id(),),
    )

    # RAMO B: completamente indipendente.
    branch_b = Transfer(
        "carol",
        "dave",
        2,
        0,
    )

    events = [
        branch_a_first,
        branch_a_conflict,
        branch_a_child,
        branch_b,
    ]

    executor = DistributedExecutor("node-1")

    result = executor.execute_view(
        initial,
        StateView.unique(initial),
        events,
    )

    # Il conflitto blocca tutto il ramo A.
    assert branch_a_first.event_id() not in result.completed
    assert branch_a_conflict.event_id() not in result.completed
    assert branch_a_child.event_id() not in result.completed

    # Il ramo B continua indipendentemente.
    assert branch_b.event_id() in result.completed

    assert result.blocked == frozenset({
        branch_a_first.event_id(),
        branch_a_conflict.event_id(),
        branch_a_child.event_id(),
    })

    assert result.state.balance("alice") == 10
    assert result.state.balance("bob") == 0
    assert result.state.balance("carol") == 8
    assert result.state.balance("dave") == 2
    assert result.state.balance("eve") == 0
