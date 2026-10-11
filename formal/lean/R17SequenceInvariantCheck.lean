import PSystem.R17Topological

namespace R17SequenceInvariantCheck

open PSystem

inductive ValidSequence (allEvents : List Event) :
    List Event → Prop
  | nil : ValidSequence allEvents []
  | append
      {processed : List Event}
      {event : Event}
      (hprev : ValidSequence allEvents processed)
      (hevent : event ∈ allEvents)
      (hfresh :
        ∀ old, old ∈ processed → old.id ≠ event.id)
      (hready : R17Ready (processed.map Event.id) event) :
      ValidSequence allEvents (processed ++ [event])

theorem sequence_subset
    (allEvents ordered : List Event)
    (hseq : ValidSequence allEvents ordered) :
    ∀ e, e ∈ ordered → e ∈ allEvents := by
  induction hseq with
  | nil =>
      intro e he
      simp at he
  | @append processed event hprev hevent hfresh hready ih =>
      intro e he
      simp only [List.mem_append, List.mem_singleton] at he
      rcases he with he | he
      · exact ih e he
      · subst e
        exact hevent


def BeforeInList
    (parent child : Event)
    (ordered : List Event) : Prop :=
  ∃ pre post,
    ordered = pre ++ parent :: post ∧
    child ∈ post

def UniqueEventIds (events : List Event) : Prop :=
  ∀ a b, a ∈ events → b ∈ events → a.id = b.id → a = b

theorem before_in_list_preserved_by_append
    (ordered : List Event)
    (parent child extra : Event)
    (hbefore : BeforeInList parent child ordered) :
    BeforeInList parent child (ordered ++ [extra]) := by
  obtain ⟨pre, post, horder, hchild⟩ := hbefore
  refine ⟨pre, post ++ [extra], ?_, ?_⟩
  · simp [horder, List.append_assoc]
  · simp [hchild]

theorem existing_parent_precedes_appended_child
    (processed : List Event)
    (parent child : Event)
    (hparent : parent ∈ processed)
    (hchild : child ∉ processed) :
    BeforeInList parent child (processed ++ [child]) := by
  induction processed with
  | nil =>
      simp at hparent
  | cons head tail ih =>
      simp only [List.mem_cons] at hparent
      simp only [List.mem_cons] at hchild
      rcases hparent with hhead | htail
      · subst head
        exact ⟨[], tail ++ [child], by simp, by simp⟩
      · obtain ⟨pre, post, horder, hchildPost⟩ :=
          ih htail (by
            intro hc
            apply hchild
            exact Or.inr hc)
        exact ⟨head :: pre, post, by
          simp [horder, List.cons_append], hchildPost⟩

theorem parent_precedes_in_valid_sequence
    (allEvents ordered : List Event)
    (hseq : ValidSequence allEvents ordered)
    (hunique : UniqueEventIds allEvents)
    (parent child : Event)
    (hparentAll : parent ∈ allEvents)
    (hchildOrdered : child ∈ ordered)
    (hdirect : DirectParent parent child) :
    BeforeInList parent child ordered := by
  induction hseq with
  | nil =>
      simp at hchildOrdered
  | @append processed event hprev hevent hfresh hready ih =>
      simp only [List.mem_append, List.mem_singleton] at hchildOrdered
      rcases hchildOrdered with hchildOld | hchildNew
      · have hbefore : BeforeInList parent child processed :=
          ih hchildOld
        exact before_in_list_preserved_by_append
          processed parent child event hbefore
      · subst child
        have hpid : parent.id ∈ processed.map Event.id :=
          hready parent.id hdirect
        obtain ⟨other, hother, hid⟩ := List.mem_map.mp hpid
        have hotherAll : other ∈ allEvents :=
          sequence_subset allEvents processed hprev other hother
        have heq : other = parent :=
          hunique other parent hotherAll hparentAll hid
        have hparentProcessed : parent ∈ processed := by
          rw [← heq]
          exact hother
        have heventFresh : event ∉ processed := by
          intro hc
          have hne := hfresh event hc
          exact hne rfl
        exact existing_parent_precedes_appended_child
          processed parent event hparentProcessed heventFresh

end R17SequenceInvariantCheck
