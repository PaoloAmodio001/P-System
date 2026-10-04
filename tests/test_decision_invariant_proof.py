from core.decision_engine import DecisionEngine
from core.decision_invariance import (
    DecisionInvariance,
    InvarianceStatus,
    KnowledgeExtension,
)
from core.decision_invariant_proof import DecisionInvariantProof
from core.decision_status import DecisionStatus
from core.event import Transfer
from core.state import State


def test_relevant_extension_changes_decision():
    visible = Transfer("alice", "bob", 5, 0)
    hidden = Transfer("alice", "carol", 5, 0)

    engine = DecisionEngine(
        state=State({"alice": 10}),
        events={visible},
    )

    result = engine.evaluate_extension(
        KnowledgeExtension(frozenset({hidden}))
    )

    assert result.before == DecisionStatus.UNIQUE
    assert result.after == DecisionStatus.CONFLICTED
    assert result.status == InvarianceStatus.CHANGED
    assert result.changed
    assert not result.invariant


def test_irrelevant_extension_preserves_decision():
    visible = Transfer("alice", "bob", 5, 0)
    unrelated = Transfer("carol", "dave", 3, 0)

    engine = DecisionEngine(
        state=State({
            "alice": 10,
            "carol": 10,
        }),
        events={visible},
    )

    result = engine.evaluate_extension(
        KnowledgeExtension(frozenset({unrelated}))
    )

    assert result.before == DecisionStatus.UNIQUE
    assert result.after == DecisionStatus.UNIQUE
    assert result.status == InvarianceStatus.INVARIANT
    assert result.invariant
    assert not result.changed


def test_empty_invariance_proof_is_not_invariant():
    engine = DecisionEngine(
        state=State({"alice": 10}),
        events=set(),
    )

    proof = engine.prove_invariance([])

    assert not proof.invariant
    assert not proof.verify()


def test_invariance_proof_rejects_changed_result():
    base = DecisionStatus.UNIQUE
    changed = DecisionInvariance(
        status=InvarianceStatus.CHANGED,
        before=base,
        after=DecisionStatus.CONFLICTED,
        extension=frozenset({"extension"}),
    )

    proof = DecisionInvariantProof.build(
        base_decision=base,
        evaluations=[changed],
        extensions=[
            KnowledgeExtension(frozenset({"extension"}))
        ],
    )

    assert not proof.invariant
    assert not proof.verify()


def test_invariance_proof_rejects_missing_evaluation():
    base = DecisionStatus.UNIQUE

    result = DecisionInvariance(
        status=InvarianceStatus.INVARIANT,
        before=base,
        after=base,
        extension=frozenset({"extension-A"}),
    )

    proof = DecisionInvariantProof(
        base_decision=base,
        evaluated_extensions=frozenset({
            frozenset({"extension-A"}),
            frozenset({"extension-B"}),
        }),
        results=frozenset({result}),
    )

    assert not proof.verify()
