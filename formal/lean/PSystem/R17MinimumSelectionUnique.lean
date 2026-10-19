import PSystem.R17MinimumSelectionBridge

namespace PSystem

theorem r17MinimumReadyEvent_unique
    (processed remaining : List Event)
    (a b : Event)
    (hunique : UniqueEventIds remaining)
    (ha :
      r17MinimumReadyEvent
        (processed.map Event.id) remaining = some a)
    (hb :
      r17MinimumReadyEvent
        (processed.map Event.id) remaining = some b) :
    a = b := by
  have hmina :
      R17MinimumReady processed remaining a :=
    r17MinimumReadyEvent_is_abstract_minimum
      processed remaining a ha
  have hminb :
      R17MinimumReady processed remaining b :=
    r17MinimumReadyEvent_is_abstract_minimum
      processed remaining b hb
  exact r17_minimum_ready_unique
    processed remaining a b hunique hmina hminb

end PSystem
