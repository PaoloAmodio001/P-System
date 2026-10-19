import PSystem.R17Constructive

namespace PSystem

/--
In a duplicate-free list, an element occurring in the tail
has an index strictly greater than the index of the head.
-/
theorem idxOf_lt_of_mem_after
    {α : Type} [BEq α] [LawfulBEq α]
    (pre post : List α)
    (a b : α)
    (hnodup : (pre ++ a :: post).Nodup)
    (hb : b ∈ post) :
    (pre ++ a :: post).idxOf a <
      (pre ++ a :: post).idxOf b := by
  have hparts := List.nodup_append.mp hnodup
  have hright := List.nodup_cons.mp hparts.2.1
  have haNotPre : a ∉ pre := by
    intro ha
    have hne := hparts.2.2 a ha a (by simp)
    exact hne rfl
  have hbNotPre : b ∉ pre := by
    intro hbp
    have hne := hparts.2.2 b hbp b (by simp [hb])
    exact hne rfl
  have hab : a ≠ b := by
    intro heq
    subst b
    exact hright.1 hb
  simp [List.idxOf_append, List.idxOf_cons,
    haNotPre, hbNotPre, hab] <;> omega

/--
A list-order witness yields a strict numerical index ordering,
provided the event IDs in the ordered list are unique.
-/
theorem beforeInList_idxOf_lt
    (ordered : List Event)
    (hnodup : (ordered.map Event.id).Nodup)
    (parent child : Event)
    (hbefore : BeforeInList parent child ordered) :
    (ordered.map Event.id).idxOf parent.id <
      (ordered.map Event.id).idxOf child.id := by
  obtain ⟨pre, post, horder, hchild⟩ := hbefore
  have hnodup' :
      (pre.map Event.id ++ parent.id :: post.map Event.id).Nodup := by
    simpa [horder, List.map_append, List.map_cons] using hnodup
  have hchildId : child.id ∈ post.map Event.id :=
    List.mem_map.mpr ⟨child, hchild, rfl⟩
  have hlt :=
    idxOf_lt_of_mem_after
      (pre.map Event.id)
      (post.map Event.id)
      parent.id
      child.id
      hnodup'
      hchildId
  simpa [horder, List.map_append, List.map_cons] using hlt


/--
Every valid R1.7 sequence has pairwise distinct event IDs.
Freshness is enforced when each event is appended.
-/
theorem r17_valid_sequence_ids_nodup
    (allEvents ordered : List Event)
    (hseq : ValidSequence allEvents ordered) :
    (ordered.map Event.id).Nodup := by
  induction hseq with
  | nil =>
      simp
  | @append processed event hprev hevent hfresh hready ih =>
      simp only [List.map_append, List.map_singleton]
      apply List.nodup_append.mpr
      refine ⟨ih, by simp, ?_⟩
      intro id hid id' hsingle
      simp only [List.mem_singleton] at hsingle
      obtain ⟨old, hold, holdId⟩ := List.mem_map.mp hid
      intro heq
      exact (hfresh old hold) (holdId.trans (heq.trans hsingle))


/-- Numeric position of an event in an R1.7 sequence, indexed by event ID. -/
def R17Position (ordered : List Event) : Position :=
  fun e => (ordered.map Event.id).idxOf e.id

/--
A complete valid R1.7 sequence refines the direct-parent ordering contract.
The event-ID uniqueness and completeness assumptions remain explicit.
-/
theorem r17_valid_sequence_refines_direct_order
    (allEvents ordered : List Event)
    (hseq : ValidSequence allEvents ordered)
    (hunique : UniqueEventIds allEvents)
    (hcomplete : ∀ e, e ∈ allEvents → e ∈ ordered) :
    DirectOrderRepresentation allEvents (R17Position ordered) := by
  intro a b ha hb hparent
  change
    (ordered.map Event.id).idxOf a.id <
      (ordered.map Event.id).idxOf b.id
  have hbefore : BeforeInList a b ordered :=
    parent_precedes_in_valid_sequence
      allEvents ordered hseq hunique a b ha (hcomplete b hb) hparent
  have hidsNodup :=
    r17_valid_sequence_ids_nodup allEvents ordered hseq
  exact beforeInList_idxOf_lt ordered hidsNodup a b hbefore


/--
Constructive R1.7 completeness directly yields a sequence that
refines the direct-parent ordering contract.
-/
theorem r17_constructive_complete_ordering_refines_direct_order
    (allEvents : List Event)
    (hunique : UniqueEventIds allEvents)
    (hparents : R17ParentsRepresented allEvents)
    (hacyclic : Acyclic allEvents) :
    ∃ ordered,
      ValidSequence allEvents ordered ∧
      (∀ e, e ∈ allEvents → e ∈ ordered) ∧
      DirectOrderRepresentation allEvents (R17Position ordered) := by
  obtain ⟨ordered, hseq, hcomplete⟩ :=
    r17_constructive_complete_ordering
      allEvents hunique hparents hacyclic
  exact ⟨ordered, hseq, hcomplete,
    r17_valid_sequence_refines_direct_order
      allEvents ordered hseq hunique hcomplete⟩

end PSystem
