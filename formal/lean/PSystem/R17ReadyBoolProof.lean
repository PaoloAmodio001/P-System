import PSystem.R17MinimumSelection

namespace PSystem

/--
The executable Boolean readiness test is equivalent to
the formal R17Ready proposition.
-/
theorem r17ReadyBool_iff_R17Ready
    (processed : List EventId)
    (event : Event) :
    r17ReadyBool processed event = true ↔
      R17Ready processed event := by
  simp [r17ReadyBool, R17Ready, List.all_eq_true]

/--
The executable filter retains exactly the events satisfying
the formal readiness predicate.
-/
theorem mem_r17ReadyEvents_iff
    (processed : List EventId)
    (remaining : List Event)
    (event : Event) :
    event ∈ r17ReadyEvents processed remaining ↔
      event ∈ remaining ∧
      R17Ready processed event := by
  simp [r17ReadyEvents, r17ReadyBool_iff_R17Ready]

end PSystem
