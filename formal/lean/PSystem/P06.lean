import PSystem.P05

namespace PSystem

/--
Extension of knowledge with one additional event.
-/
def ExtendKnowledge
    (knowledge : Knowledge)
    (e : Event) : Knowledge :=
  knowledge ++ [e]

/--
An event is irrelevant when it cannot affect the relevance projection.
-/
def Irrelevant
    (relevant : Relevance)
    (e : Event) : Prop :=
  ¬ relevant e

/--
P06 — Adding an irrelevant event does not change the relevant
knowledge projection.
-/
theorem P06_irrelevant_extension_preserves_relevant_projection
    (relevant : Relevance)
    (knowledge : Knowledge)
    (e : Event)
    (h_irrelevant : Irrelevant relevant e) :
    RelevantKnowledge relevant (ExtendKnowledge knowledge e) =
      RelevantKnowledge relevant knowledge := by
  have h_not_relevant : ¬ relevant e := h_irrelevant
  simp [ExtendKnowledge, RelevantKnowledge, h_not_relevant]

/--
P06 — Adding an irrelevant event does not change the decision.
-/
theorem P06_irrelevant_extension_preserves_decision
    (relevant : Relevance)
    (decideFn : DecisionFunction)
    (knowledge : Knowledge)
    (e : Event)
    (h_irrelevant : Irrelevant relevant e) :
    Decision relevant decideFn (ExtendKnowledge knowledge e) =
      Decision relevant decideFn knowledge := by
  unfold Decision
  rw [P06_irrelevant_extension_preserves_relevant_projection
    relevant knowledge e h_irrelevant]

end PSystem
