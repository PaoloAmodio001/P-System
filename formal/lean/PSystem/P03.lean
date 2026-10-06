import PSystem.Basic

namespace PSystem

/--
P03 — Conflicting events cannot both belong to a compatible
execution projection.
-/
theorem P03_conflict_excludes_compatibility
    (a b : Event)
    (hconflict : Conflict a b) :
    ¬ Compatible [a, b] := by
  exact conflict_implies_not_compatible a b hconflict

/--
If an event set is compatible, every pair of events in it
is non-conflicting.
-/
theorem P03_compatible_pair_not_conflict
    (events : List Event)
    (hcompat : Compatible events)
    (a b : Event)
    (ha : a ∈ events)
    (hb : b ∈ events) :
    ¬ Conflict a b := by
  exact compatible_pair_not_conflict events hcompat a b ha hb

end PSystem
