import PSystem.R17Topological

namespace R17OrderInvariantCheck

open PSystem

def BeforeInList {α : Type}
    (parent child : α) (ordered : List α) : Prop :=
  ∃ pre post,
    ordered = pre ++ parent :: post ∧
    child ∈ post

def UniqueEventIds (events : List Event) : Prop :=
  ∀ a b, a ∈ events → b ∈ events → a.id = b.id → a = b

theorem ready_parent_is_processed
    (processed : List Event)
    (child : Event)
    (hready : R17Ready (processed.map Event.id) child)
    (parentId : EventId)
    (hparent : parentId ∈ child.parents) :
    parentId ∈ processed.map Event.id := by
  exact hready parentId hparent

theorem unique_ids_preserved_by_append
    (processed : List Event)
    (selected : Event)
    (hunique : UniqueEventIds processed)
    (hfresh : ∀ e, e ∈ processed → e.id ≠ selected.id) :
    UniqueEventIds (processed ++ [selected]) := by
  intro a b ha hb hid
  simp only [List.mem_append, List.mem_singleton] at ha hb
  rcases ha with ha | ha
  · rcases hb with hb | hb
    · exact hunique a b ha hb hid
    · subst b
      exact False.elim (hfresh a ha hid)
  · subst a
    rcases hb with hb | hb
    · exact False.elim (hfresh b hb hid.symm)
    · subst b
      rfl

end R17OrderInvariantCheck
