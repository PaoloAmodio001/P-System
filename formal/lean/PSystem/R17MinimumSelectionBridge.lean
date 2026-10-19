import PSystem.R17ReadyBoolProof
import PSystem.R17Deterministic

namespace PSystem

theorem r17MinimumReadyEvent_is_abstract_minimum
    (processed remaining : List Event)
    (event : Event)
    (hsel :
      r17MinimumReadyEvent
        (processed.map Event.id) remaining = some event) :
    R17MinimumReady processed remaining event := by
  constructor
  · constructor
    · have hmem :
          event ∈ r17ReadyEvents
            (processed.map Event.id) remaining := by
        unfold r17MinimumReadyEvent at hsel
        dsimp only at hsel
        cases hmin :
            (r17ReadyEvents
              (processed.map Event.id) remaining).map Event.id |>.min? with
        | none =>
            simp [hmin] at hsel
        | some minId =>
            simp only [hmin] at hsel
            exact List.mem_of_find?_eq_some hsel
      exact
        ((mem_r17ReadyEvents_iff
          (processed.map Event.id) remaining event).mp hmem).1
    · exact
        ((mem_r17ReadyEvents_iff
          (processed.map Event.id) remaining event).mp
          (by
            unfold r17MinimumReadyEvent at hsel
            dsimp only at hsel
            cases hmin :
                (r17ReadyEvents
                  (processed.map Event.id) remaining).map Event.id |>.min? with
            | none => simp [hmin] at hsel
            | some minId =>
                simp only [hmin] at hsel
                exact List.mem_of_find?_eq_some hsel)).2
  · intro other hother
    apply r17MinimumReadyEvent_is_minimal
      (processed.map Event.id) remaining event hsel other
    exact
      (mem_r17ReadyEvents_iff
        (processed.map Event.id) remaining other).mpr
        ⟨hother.1, hother.2⟩

end PSystem
