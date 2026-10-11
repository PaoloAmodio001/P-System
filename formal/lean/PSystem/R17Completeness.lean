import PSystem.R17Topological

namespace PSystem

/--
R1.7 — Conditional completeness of a valid ordering.

If every input event occurs in the ordered sequence, then together
with sequence_subset the two lists have the same event membership.
Completeness itself remains an explicit premise.
-/
theorem r17_complete_membership
    (allEvents ordered : List Event)
    (hseq : ValidSequence allEvents ordered)
    (hcomplete : ∀ e, e ∈ allEvents → e ∈ ordered) :
    ∀ e, e ∈ ordered ↔ e ∈ allEvents := by
  intro e
  constructor
  · intro hordered
    exact sequence_subset allEvents ordered hseq e hordered
  · exact hcomplete e

end PSystem
