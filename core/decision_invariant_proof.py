from dataclasses import dataclass
from typing import FrozenSet, Generic, TypeVar

from core.decision_invariance import (
    DecisionInvariance,
    InvarianceStatus,
    KnowledgeExtension,
)


T = TypeVar("T")
D = TypeVar("D")


@dataclass(frozen=True)
class DecisionInvariantProof(Generic[T, D]):
    """
    Evidence that a decision remained unchanged for every
    explicitly evaluated extension.

    This is NOT a proof of global completeness.

    It proves only that all supplied extensions were evaluated
    and none of them changed the decision.
    """

    base_decision: D
    evaluated_extensions: FrozenSet[frozenset[T]]
    results: FrozenSet[DecisionInvariance]

    @property
    def invariant(self) -> bool:
        if not self.evaluated_extensions:
            return False

        return all(
            result.status == InvarianceStatus.INVARIANT
            for result in self.results
        )

    @classmethod
    def build(
        cls,
        base_decision: D,
        evaluations: list[DecisionInvariance],
        extensions: list[KnowledgeExtension[T]],
    ) -> "DecisionInvariantProof[T, D]":

        if len(evaluations) != len(extensions):
            raise ValueError(
                "EVALUATION/EXTENSION COUNT MISMATCH"
            )

        if any(
            evaluation.before != base_decision
            for evaluation in evaluations
        ):
            raise ValueError(
                "BASE DECISION MISMATCH"
            )

        return cls(
            base_decision=base_decision,
            evaluated_extensions=frozenset(
                extension.added
                for extension in extensions
            ),
            results=frozenset(evaluations),
        )

    def verify(self) -> bool:
        if not self.evaluated_extensions:
            return False

        if not self.results:
            return False

        evaluated = frozenset(
            result.extension
            for result in self.results
        )

        if evaluated != self.evaluated_extensions:
            return False

        if any(
            result.before != self.base_decision
            for result in self.results
        ):
            return False

        if any(
            result.status != InvarianceStatus.INVARIANT
            for result in self.results
        ):
            return False

        return True
