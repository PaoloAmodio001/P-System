import PSystem.R17Deterministic

namespace PSystem


theorem r17_minimum_id_spec
    (ids : List EventId)
    (minId : EventId)
    (hmin : ids.min? = some minId) :
    minId ∈ ids ∧
      ∀ other, other ∈ ids → minId ≤ other := by
  exact List.min?_eq_some_iff.mp hmin

end PSystem
