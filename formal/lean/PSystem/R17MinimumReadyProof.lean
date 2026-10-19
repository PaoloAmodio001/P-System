import PSystem.R17MinimumProof

namespace PSystem

/--
If the minimum identifier of a list of event identifiers exists,
it is no greater than any identifier in that list.
-/
theorem r17_minimum_id_le
    (ids : List EventId)
    (minId : EventId)
    (hmin : ids.min? = some minId)
    (other : EventId)
    (hother : other ∈ ids) :
    minId ≤ other := by
  exact (r17_minimum_id_spec ids minId hmin).2 other hother

end PSystem
