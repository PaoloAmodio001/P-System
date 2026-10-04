from dataclasses import dataclass
from enum import Enum
from typing import Callable, FrozenSet, TypeVar


T = TypeVar("T")
D = TypeVar("D")


class InvarianceStatus(Enum):
    INVARIANT = "INVARIANT"
    CHANGED = "CHANGED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class KnowledgeExtension:
    """
    An explicit extension of the currently known information.

    The extension is intentionally represented separately from the
    current knowledge: knowing that an extension exists is different
    from assuming that no extension exists.
    """

    added: FrozenSet[T]

    def extend(self, knowledge: FrozenSet[T]) -> FrozenSet[T]:
        return knowledge | self.added


@dataclass(frozen=True)
class DecisionInvariance:
    """
    Result of comparing a decision before and after an extension.

    INVARIANT:
        the decision is unchanged for the evaluated extension.

    CHANGED:
        the extension changes the decision.

    UNKNOWN:
        no conclusion about invariance can be established.
    """

    status: InvarianceStatus
    before: D
    after: D
    extension: FrozenSet[T]

    @property
    def invariant(self) -> bool:
        return self.status == InvarianceStatus.INVARIANT

    @property
    def changed(self) -> bool:
        return self.status == InvarianceStatus.CHANGED

    @classmethod
    def evaluate(
        cls,
        knowledge: FrozenSet[T],
        extension: KnowledgeExtension[T],
        decide: Callable[[FrozenSet[T]], D],
    ) -> "DecisionInvariance":

        before = decide(knowledge)
        after = decide(extension.extend(knowledge))

        if before == after:
            status = InvarianceStatus.INVARIANT
        else:
            status = InvarianceStatus.CHANGED

        return cls(
            status=status,
            before=before,
            after=after,
            extension=extension.added,
        )


def evaluate_extension(
    knowledge: FrozenSet[T],
    extension: KnowledgeExtension[T],
    decide: Callable[[FrozenSet[T]], D],
) -> DecisionInvariance:
    """
    Evaluate one explicit knowledge extension.

    Important:
    this function does NOT prove global completeness and does NOT
    prove that the evaluated extension is the only possible extension.
    It only establishes the relationship between the current
    decision and the supplied extension.
    """

    return DecisionInvariance.evaluate(
        knowledge=knowledge,
        extension=extension,
        decide=decide,
    )
