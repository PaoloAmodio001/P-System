from dataclasses import dataclass
from typing import FrozenSet, Generic, TypeVar

from core.conflict_state import ConflictState
from core.decision_invariance import (
    DecisionInvariance,
    KnowledgeExtension,
    evaluate_extension,
)
from core.decision_invariant_proof import DecisionInvariantProof
from core.decision_status import (
    DecisionStatus,
    classify_decision,
)
from core.impact_closure import (
    ImpactClosure,
    build_impact_closure,
)
from core.partial_knowledge import PartialKnowledge
from core.relevance import (
    RelevanceRegion,
    build_relevance_region,
)
from core.relevance_graph import RelevanceGraph
from core.uncertainty_boundary import (
    UncertaintyBoundary,
    analyze_boundary,
)
from core.event import Transfer
from core.state import State


D = TypeVar("D")


@dataclass(frozen=True)
class DecisionContext:
    knowledge: PartialKnowledge
    region: RelevanceRegion
    impact: ImpactClosure
    boundary: UncertaintyBoundary
    conflict: ConflictState
    status: DecisionStatus


class DecisionEngine:
    """
    Central decision engine for X-System.

    Pipeline:

        knowledge
            ↓
        relevance region
            ↓
        impact closure
            ↓
        uncertainty boundary
            ↓
        conflict analysis
            ↓
        decision status

    The engine never assumes global completeness.
    """

    def __init__(
        self,
        state: State,
        events: FrozenSet[Transfer] | set[Transfer] | None = None,
        relevance_graph: RelevanceGraph | None = None,
        conflict: ConflictState | None = None,
    ):
        self.state = state.copy()

        self.events = frozenset(
            events or frozenset()
        )

        self.relevance_graph = relevance_graph
        self.external_conflict = conflict

    def knowledge(self) -> PartialKnowledge:
        return PartialKnowledge(
            events=self.events
        )

    def region(self) -> RelevanceRegion:
        return build_relevance_region(
            self.state,
            list(self.events),
        )

    def impact(self) -> ImpactClosure:
        region = self.region()

        if self.relevance_graph is None:
            return ImpactClosure(
                nodes=region.nodes
            )

        return build_impact_closure(
            region,
            self.relevance_graph,
        )

    def boundary(self) -> UncertaintyBoundary:
        knowledge = self.knowledge()

        if self.relevance_graph is None:
            missing = knowledge.missing_parents()

            return UncertaintyBoundary(
                known=knowledge.event_ids(),
                potentially_relevant=missing,
                irrelevant=frozenset(),
            )

        region = self.region()

        boundary = analyze_boundary(
            {
                node.key()
                for node in region.nodes
            },
            self.relevance_graph,
        )

        missing = knowledge.missing_parents()

        if not missing:
            return boundary

        return UncertaintyBoundary(
            known=boundary.known,
            potentially_relevant=(
                boundary.potentially_relevant
                | missing
            ),
            irrelevant=boundary.irrelevant,
        )

    def conflict(self) -> ConflictState:
        if self.external_conflict is not None:
            return self.external_conflict

        return ConflictState(
            tuple(
                sorted(
                    self.events,
                    key=lambda event: event.event_id(),
                )
            )
        )

    def status(self) -> DecisionStatus:
        return classify_decision(
            self.boundary(),
            self.conflict(),
        )

    def context(self) -> DecisionContext:
        return DecisionContext(
            knowledge=self.knowledge(),
            region=self.region(),
            impact=self.impact(),
            boundary=self.boundary(),
            conflict=self.conflict(),
            status=self.status(),
        )

    def evaluate_extension(
        self,
        extension: KnowledgeExtension[Transfer],
    ) -> DecisionInvariance:
        current = self.events

        def decide(
            knowledge: FrozenSet[Transfer],
        ) -> DecisionStatus:
            engine = DecisionEngine(
                state=self.state,
                events=knowledge,
                relevance_graph=self.relevance_graph,
            )

            return engine.status()

        return evaluate_extension(
            knowledge=current,
            extension=extension,
            decide=decide,
        )

    def prove_invariance(
        self,
        extensions: list[KnowledgeExtension[Transfer]],
    ) -> DecisionInvariantProof[
        Transfer,
        DecisionStatus,
    ]:
        base_decision = self.status()

        evaluations = [
            self.evaluate_extension(extension)
            for extension in extensions
        ]

        return DecisionInvariantProof.build(
            base_decision=base_decision,
            evaluations=evaluations,
            extensions=extensions,
        )
