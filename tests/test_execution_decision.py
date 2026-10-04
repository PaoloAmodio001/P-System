from core.execution_decision import decide
from core.execution_relations import ExecutionRelations


def test_conflicting_events_are_not_executable():
    relations = ExecutionRelations(
        causal=(
            ("a", "b"),
        ),
        parallel=(
            ("a", "c"),
        ),
        conflicts=(
            ("d", "e"),
        ),
    )

    decision = decide(relations)

    assert "a" in decision.executable
    assert "b" in decision.executable
    assert "c" in decision.executable

    assert "d" not in decision.executable
    assert "e" not in decision.executable

    assert decision.has_conflicts()
