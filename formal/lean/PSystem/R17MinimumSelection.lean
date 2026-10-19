import PSystem.R17MinimumProof

namespace PSystem

def r17ReadyBool
    (processed : List EventId)
    (event : Event) : Bool :=
  event.parents.all
    (fun parentId => processed.contains parentId)

def r17ReadyEvents
    (processed : List EventId)
    (remaining : List Event) : List Event :=
  remaining.filter
    (fun event => r17ReadyBool processed event)

def r17MinimumReadyEvent
    (processed : List EventId)
    (remaining : List Event) : Option Event :=
  let ready := r17ReadyEvents processed remaining
  match (ready.map Event.id).min? with
  | none => none
  | some minId =>
      ready.find? (fun event => decide (event.id = minId))

theorem r17MinimumReadyEvent_is_minimal
    (processed : List EventId)
    (remaining : List Event)
    (event : Event)
    (hsel : r17MinimumReadyEvent processed remaining = some event)
    (other : Event)
    (hother : other ∈ r17ReadyEvents processed remaining) :
    event.id ≤ other.id := by
  change
    (match (r17ReadyEvents processed remaining).map Event.id |>.min? with
     | none => none
     | some minId =>
         (r17ReadyEvents processed remaining).find?
           (fun e => decide (e.id = minId))) = some event at hsel
  cases hmin :
      (r17ReadyEvents processed remaining).map Event.id |>.min? with
  | none =>
      simp [hmin] at hsel
  | some minId =>
      simp only [hmin] at hsel
      have hfound :
          (r17ReadyEvents processed remaining).find?
            (fun e => decide (e.id = minId)) = some event := hsel
      have hpred := List.find?_some hfound
      have hmem : event ∈ r17ReadyEvents processed remaining := by
        have hmem' :
            event ∈ r17ReadyEvents processed remaining := by
          exact List.mem_of_find?_eq_some hfound
        exact hmem'
      have heq : event.id = minId := of_decide_eq_true hpred
      have hle :
          minId ≤ other.id :=
        (List.min?_eq_some_iff.mp hmin).2 other.id
          (List.mem_map.mpr ⟨other, hother, rfl⟩)
      simpa [heq] using hle

end PSystem
