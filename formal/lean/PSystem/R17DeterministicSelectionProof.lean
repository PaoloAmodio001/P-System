import PSystem.R17MinimumSelectionBridge

namespace PSystem

theorem r17_minimum_selection_exists
    (processed : List EventId)
    (remaining : List Event)
    (hne : r17ReadyEvents processed remaining ≠ []) :
    ∃ event, r17MinimumReadyEvent processed remaining = some event := by
  unfold r17MinimumReadyEvent
  let ready := r17ReadyEvents processed remaining
  have hready : ready ≠ [] := hne
  have hmap : ready.map Event.id ≠ [] := by
    cases hreadyList : ready with
    | nil => exact False.elim (hready hreadyList)
    | cons head tail => simp
  have hmin : (ready.map Event.id).min? ≠ none := by
    intro hnone
    have hempty : ready.map Event.id = [] :=
      (List.min?_eq_none_iff).mp hnone
    exact hmap hempty
  cases hvalue : (ready.map Event.id).min? with
  | none =>
      exact False.elim (hmin hvalue)
  | some minId =>
      have hminMem : minId ∈ ready.map Event.id :=
        (List.min?_eq_some_iff.mp hvalue).1
      obtain ⟨candidate, hcandidate, hid⟩ :=
        List.mem_map.mp hminMem
      have hfindExists :
          ∃ event, event ∈ ready ∧
            decide (event.id = minId) = true := by
        refine ⟨candidate, hcandidate, ?_⟩
        simp [hid]
      have hsome :
          (ready.find? (fun event =>
            decide (event.id = minId))).isSome = true :=
        (List.find?_isSome).2 hfindExists
      cases hresult : ready.find? (fun event =>
          decide (event.id = minId)) with
      | none =>
          simp [hresult] at hsome
      | some event =>
          refine ⟨event, ?_⟩
          change
            (match (ready.map Event.id).min? with
             | none => none
             | some id => ready.find? (fun e => decide (e.id = id))) =
            some event
          simp only [hvalue]
          exact hresult


end PSystem
