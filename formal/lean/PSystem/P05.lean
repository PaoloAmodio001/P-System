import PSystem.Basic

namespace PSystem

/--
Knowledge is represented by a finite event list.
-/
abbrev Knowledge := List Event

/--
A relevance predicate identifies events that may affect a decision.
-/
abbrev Relevance := Event → Prop

/--
The relevant projection of knowledge.
-/
noncomputable def RelevantKnowledge
    (relevant : Relevance)
    (knowledge : Knowledge) : Knowledge := by
  classical
  exact knowledge.filter (fun e => decide (relevant e))

/--
Abstract deterministic decision function over relevant knowledge.
-/
abbrev DecisionFunction :=
  Knowledge → Option Event

/--
Decision induced by a decision function and a relevance predicate.
Only relevant knowledge is visible to the decision function.
-/
noncomputable def Decision
    (relevant : Relevance)
    (decideFn : DecisionFunction)
    (knowledge : Knowledge) : Option Event :=
  decideFn (RelevantKnowledge relevant knowledge)

/--
P05 — Decision dependence is restricted to relevant knowledge.

Two knowledge states with the same relevant projection produce
the same decision.
-/
theorem P05_relevant_knowledge_determines_decision
    (relevant : Relevance)
    (decideFn : DecisionFunction)
    (k1 k2 : Knowledge)
    (h :
      RelevantKnowledge relevant k1 =
      RelevantKnowledge relevant k2) :
    Decision relevant decideFn k1 =
      Decision relevant decideFn k2 := by
  simp [Decision, h]

/--
An uncertainty boundary records known and potentially relevant
knowledge not yet incorporated into the decision projection.
-/
structure UncertaintyBoundary where
  known : Knowledge
  potentiallyRelevant : Knowledge
  irrelevant : Knowledge

/--
A boundary is closed when no potentially relevant event remains.
-/
def BoundaryClosed
    (boundary : UncertaintyBoundary) : Prop :=
  boundary.potentiallyRelevant = []

/--
P05 — A non-empty potentially relevant boundary prevents a claim
that the relevant knowledge domain is fully closed.
-/
theorem P05_open_boundary_blocks_closure
    (boundary : UncertaintyBoundary)
    (h_open : boundary.potentiallyRelevant ≠ []) :
    ¬ BoundaryClosed boundary := by
  intro h_closed
  exact h_open h_closed

end PSystem
