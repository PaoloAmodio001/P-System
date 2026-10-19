import PSystem.R17Topological

namespace PSystem

/-!
R1.7 — Constructive completeness groundwork.
This module keeps the existing conditional theorem separate while
we develop a constructive ordering proof.
-/

/--
Every declared parent ID resolves to an event in the input collection.
This is an explicit graph-closure requirement for the constructive proof.
-/
def R17ParentsRepresented (allEvents : List Event) : Prop :=
  ∀ child, child ∈ allEvents →
    ∀ parentId, parentId ∈ child.parents →
      ∃ parent, parent ∈ allEvents ∧ parent.id = parentId

/-- Every event in a valid sequence belongs to the input collection. -/
theorem r17_constructive_sequence_subset
    (allEvents ordered : List Event)
    (hseq : ValidSequence allEvents ordered) :
    ∀ e, e ∈ ordered → e ∈ allEvents := by
  exact sequence_subset allEvents ordered hseq

/-- A valid sequence has no repeated event identifiers. -/
theorem r17_constructive_unique_ids
    (allEvents ordered : List Event)
    (hseq : ValidSequence allEvents ordered) :
    UniqueEventIds ordered := by
  exact r17_valid_sequence_unique_ids allEvents ordered hseq

/--
An event is ready when none of its declared parent IDs belongs
to an event still waiting to be processed.
-/
def R17ReadyInRemaining (remaining : List Event) (event : Event) : Prop :=
  ∀ parentId, parentId ∈ event.parents →
    ∀ parent, parent ∈ remaining → parent.id = parentId → False

/--
Readiness is equivalent to having no direct parent among the remaining events.
-/
theorem r17_ready_iff_no_remaining_parent
    (remaining : List Event)
    (event : Event) :
    R17ReadyInRemaining remaining event ↔
      ∀ parent, parent ∈ remaining → ¬ DirectParent parent event := by
  constructor
  · intro h parent hparent hdirect
    exact h parent.id hdirect parent hparent rfl
  · intro h parentId hparentId parent hparent heq
    apply h parent hparent
    subst parentId
    exact hparentId

/--
If an event is not ready, one of its direct parents is still remaining.
-/
theorem r17_not_ready_has_remaining_parent
    (remaining : List Event)
    (event : Event)
    (hnotready : ¬ R17ReadyInRemaining remaining event) :
    ∃ parent, parent ∈ remaining ∧ DirectParent parent event := by
  have h := hnotready
  rw [r17_ready_iff_no_remaining_parent] at h
  exact Classical.byContradiction (fun hexists =>
    h (fun parent hmem hdirect =>
      hexists ⟨parent, hmem, hdirect⟩))

/--
If no remaining event is ready, every remaining event has a
direct parent that is also still remaining.
-/
theorem r17_no_ready_implies_remaining_parent
    (remaining : List Event)
    (hnoReady :
      ∀ event, event ∈ remaining → ¬ R17ReadyInRemaining remaining event) :
    ∀ event, event ∈ remaining →
      ∃ parent, parent ∈ remaining ∧ DirectParent parent event := by
  intro event hevent
  exact r17_not_ready_has_remaining_parent
    remaining event (hnoReady event hevent)

/-- A nonempty finite acyclic list has a causal minimum. -/
theorem r17_exists_causally_minimal
    (allEvents remaining : List Event)
    (hsub : ∀ e, e ∈ remaining → e ∈ allEvents)
    (hacyclic : Acyclic allEvents)
    (hne : remaining ≠ []) :
    ∃ event, event ∈ remaining ∧
      ∀ parent, parent ∈ remaining → ¬ CausalBefore parent event := by
  revert hsub hne
  induction remaining with
  | nil =>
      intro hsub hne
      exact False.elim (hne rfl)
  | cons head tail ih =>
      intro hsub hne
      have hs : ∀ e, e ∈ tail → e ∈ allEvents := by
        intro e he
        exact hsub e (by simp [he])
      by_cases hno : ∀ parent, parent ∈ tail → ¬ CausalBefore parent head
      · refine ⟨head, by simp, ?_⟩
        intro parent hp hcausal
        simp only [List.mem_cons] at hp
        rcases hp with heq | htail
        · subst parent
          exact hacyclic head (hsub head (by simp)) hcausal
        · exact hno parent htail hcausal
      · have hex : ∃ parent, parent ∈ tail ∧ CausalBefore parent head :=
          Classical.byContradiction (fun hn =>
            hno (fun parent hp hcausal => hn ⟨parent, hp, hcausal⟩))
        have htailne : tail ≠ [] := by
          intro ht
          subst tail
          obtain ⟨parent, hp, hcausal⟩ := hex
          simp at hp
        obtain ⟨minimal, hmem, hmin⟩ := ih hs htailne
        refine ⟨minimal, by simp [hmem], ?_⟩
        intro parent hp hcausal
        simp only [List.mem_cons] at hp
        rcases hp with heq | htail
        · subst parent
          obtain ⟨earlier, hearlierMem, hearlierHead⟩ := hex
          exact hmin earlier hearlierMem
            (CausalBefore.trans hearlierHead hcausal)
        · exact hmin parent htail hcausal

/-- Every nonempty acyclic remainder contains a ready event. -/
theorem r17_exists_ready_event
    (allEvents remaining : List Event)
    (hsub : ∀ e, e ∈ remaining → e ∈ allEvents)
    (hacyclic : Acyclic allEvents)
    (hne : remaining ≠ []) :
    ∃ event, event ∈ remaining ∧ R17ReadyInRemaining remaining event := by
  obtain ⟨event, hevent, hminimal⟩ :=
    r17_exists_causally_minimal allEvents remaining hsub hacyclic hne
  refine ⟨event, hevent, ?_⟩
  apply (r17_ready_iff_no_remaining_parent remaining event).2
  intro parent hparent hdirect
  exact hminimal parent hparent (CausalBefore.direct hdirect)

/--
Every declared parent of a ready event belongs to the processed prefix,
provided every input event is either processed or still remaining.
-/
theorem r17_ready_parents_in_processed
    (allEvents processed remaining : List Event)
    (hparents : R17ParentsRepresented allEvents)
    (hremaining : ∀ e, e ∈ remaining → e ∈ allEvents)
    (hpartition :
      ∀ e, e ∈ allEvents → e ∈ processed ∨ e ∈ remaining)
    (event : Event)
    (hevent : event ∈ remaining)
    (hready : R17ReadyInRemaining remaining event) :
    ∀ parentId, parentId ∈ event.parents →
      parentId ∈ processed.map Event.id := by
  intro parentId hparentId
  obtain ⟨parent, hparentAll, hid⟩ :=
    hparents event (hremaining event hevent) parentId hparentId
  have hwhere := hpartition parent hparentAll
  rcases hwhere with hprocessed | hstill
  · exact List.mem_map.mpr ⟨parent, hprocessed, hid⟩
  · exact False.elim (hready parentId hparentId parent hstill hid)

/--
Selecting an event and filtering its ID from the remainder preserves
the partition of the input events into processed and remaining events.
-/
theorem r17_filter_preserves_partition
    (allEvents processed remaining : List Event)
    (hunique : UniqueEventIds allEvents)
    (hremaining : ∀ e, e ∈ remaining → e ∈ allEvents)
    (hpartition :
      ∀ e, e ∈ allEvents → e ∈ processed ∨ e ∈ remaining)
    (selected : Event)
    (hselected : selected ∈ remaining) :
    ∀ e, e ∈ allEvents →
      e ∈ processed ++ [selected] ∨
        e ∈ remaining.filter (fun event => event.id != selected.id) := by
  intro e he
  rcases hpartition e he with hp | hr
  · left
    simp [hp]
  · by_cases hid : e.id = selected.id
    · have heq : e = selected :=
        hunique e selected he
          (hremaining selected hselected) hid
      left
      simp [heq]
    · right
      exact List.mem_filter.mpr ⟨hr, by simp [hid]⟩

/--
Selecting an event and filtering it from the remainder preserves
ID-disjointness between the processed prefix and the new remainder.
-/
theorem r17_filter_preserves_disjoint_ids
    (processed remaining : List Event)
    (hdisjoint :
      ∀ p, p ∈ processed → ∀ r, r ∈ remaining → p.id ≠ r.id)
    (selected : Event)
    (_hselected : selected ∈ remaining) :
    ∀ p, p ∈ processed →
      ∀ r, r ∈ remaining.filter
        (fun event => event.id != selected.id) →
      p.id ≠ r.id := by
  intro p hp r hr
  have hrmem : r ∈ remaining :=
    (List.mem_filter.mp hr).1
  exact hdisjoint p hp r hrmem

/--
The selected event has an ID different from every event in the
filtered remainder, because the filter removes its ID.
-/
theorem r17_selected_disjoint_filtered_remainder
    (remaining : List Event)
    (selected : Event)
    (_hselected : selected ∈ remaining) :
    ∀ r, r ∈ remaining.filter
      (fun event => event.id != selected.id) →
    selected.id ≠ r.id := by
  intro r hr
  have hfilter := (List.mem_filter.mp hr).2
  have hne : r.id ≠ selected.id := by
    simpa using hfilter
  exact Ne.symm hne


/--
Filtering a list strictly decreases its length if at least one
element of the list fails the Boolean predicate.
-/
theorem r17_filter_length_lt_of_rejected
    {α : Type} (items : List α) (keep : α → Bool)
    (x : α) (hx : x ∈ items) (hrejected : keep x = false) :
    (items.filter keep).length < items.length := by
  apply Nat.lt_of_le_of_ne (List.length_filter_le keep items)
  intro heq
  have hall : ∀ a, a ∈ items → keep a = true :=
    (List.length_filter_eq_length_iff).1 heq
  exact Bool.noConfusion (hall x hx |>.symm.trans hrejected)

/--
Removing the selected event ID strictly decreases the remainder length.
-/
theorem r17_filter_selected_length_lt
    (remaining : List Event)
    (selected : Event)
    (hselected : selected ∈ remaining) :
    (remaining.filter
      (fun event => event.id != selected.id)).length <
        remaining.length := by
  apply r17_filter_length_lt_of_rejected
    remaining (fun event => event.id != selected.id)
    selected hselected
  simp


/--
Extend a valid processed prefix until every input event is either
already processed or belongs to the newly constructed suffix.

Termination is justified by the strict decrease of the remaining
list after each selected event is filtered out.
-/
theorem r17_constructive_extend
    (allEvents processed remaining : List Event)
    (hunique : UniqueEventIds allEvents)
    (hparents : R17ParentsRepresented allEvents)
    (hacyclic : Acyclic allEvents)
    (hremaining : ∀ e, e ∈ remaining → e ∈ allEvents)
    (hpartition :
      ∀ e, e ∈ allEvents → e ∈ processed ∨ e ∈ remaining)
    (hdisjoint :
      ∀ p, p ∈ processed → ∀ r, r ∈ remaining → p.id ≠ r.id)
    (hseq : ValidSequence allEvents processed) :
    ∃ suffix,
      ValidSequence allEvents (processed ++ suffix) ∧
      (∀ e, e ∈ allEvents → e ∈ processed ∨ e ∈ suffix) := by
  by_cases hempty : remaining = []
  · refine ⟨[], ?_, ?_⟩
    · simpa using hseq
    · intro e he
      rcases hpartition e he with hp | hr
      · exact Or.inl hp
      · simp [hempty] at hr
  · obtain ⟨selected, hselected, hreadyRemaining⟩ :=
      r17_exists_ready_event
        allEvents remaining hremaining hacyclic hempty
    have hready : R17Ready (processed.map Event.id) selected := by
      intro parentId hparentId
      exact r17_ready_parents_in_processed
        allEvents processed remaining hparents hremaining hpartition
        selected hselected hreadyRemaining parentId hparentId
    have hfresh :
        ∀ old, old ∈ processed → old.id ≠ selected.id := by
      intro old hold
      exact hdisjoint old hold selected hselected
    have hseqNext :
        ValidSequence allEvents (processed ++ [selected]) :=
      ValidSequence.append hseq
        (hremaining selected hselected) hfresh hready
    let remainingNext :=
      remaining.filter (fun event => event.id != selected.id)
    have hremainingNext :
        ∀ e, e ∈ remainingNext → e ∈ allEvents := by
      intro e he
      exact hremaining e (List.mem_filter.mp he).1
    have hpartitionNext :
        ∀ e, e ∈ allEvents →
          e ∈ processed ++ [selected] ∨ e ∈ remainingNext := by
      intro e he
      exact r17_filter_preserves_partition
        allEvents processed remaining hunique hremaining hpartition
        selected hselected e he
    have hdisjointNext :
        ∀ p, p ∈ processed ++ [selected] →
          ∀ r, r ∈ remainingNext → p.id ≠ r.id := by
      intro p hp r hr
      simp only [List.mem_append, List.mem_singleton] at hp
      rcases hp with hp | hp
      · exact hdisjoint p hp r (List.mem_filter.mp hr).1
      · subst p
        exact r17_selected_disjoint_filtered_remainder
          remaining selected hselected r hr
    obtain ⟨suffix, hseqFinal, hcompleteFinal⟩ :=
      r17_constructive_extend
        allEvents (processed ++ [selected]) remainingNext
        hunique hparents hacyclic hremainingNext hpartitionNext
        hdisjointNext hseqNext
    refine ⟨selected :: suffix, ?_, ?_⟩
    · simpa [List.append_assoc] using hseqFinal
    · intro e he
      rcases hcompleteFinal e he with hp | hs
      · simp only [List.mem_append, List.mem_singleton] at hp
        rcases hp with hp | hsel
        · exact Or.inl hp
        · subst e
          exact Or.inr (by simp)
      · exact Or.inr (by simp [hs])
termination_by remaining.length
decreasing_by
  simpa [remainingNext] using
    r17_filter_selected_length_lt remaining selected hselected


/--
R1.7 — Constructive completeness of topological ordering.

For a finite collection of events with unique IDs, represented parent
IDs, and an acyclic causal relation, there exists a valid sequence
containing every input event.
-/
theorem r17_constructive_complete_ordering
    (allEvents : List Event)
    (hunique : UniqueEventIds allEvents)
    (hparents : R17ParentsRepresented allEvents)
    (hacyclic : Acyclic allEvents) :
    ∃ ordered, ValidSequence allEvents ordered ∧
      (∀ e, e ∈ allEvents → e ∈ ordered) := by
  obtain ⟨ordered, hseq, hcomplete⟩ :=
    r17_constructive_extend
      allEvents [] allEvents
      hunique hparents hacyclic
      (by
        intro e he
        exact he)
      (by
        intro e he
        exact Or.inr he)
      (by
        intro p hp
        simp at hp)
      ValidSequence.nil
  refine ⟨ordered, ?_, ?_⟩
  · simpa using hseq
  · intro e he
    rcases hcomplete e he with hp | ho
    · simp at hp
    · exact ho

/-- A represented parent ID determines a direct parent event. -/
theorem r17_resolved_parent_is_direct
    (allEvents : List Event)
    (hparents : R17ParentsRepresented allEvents)
    (child : Event)
    (hchild : child ∈ allEvents)
    (parentId : EventId)
    (hparentId : parentId ∈ child.parents) :
    ∃ parent, parent ∈ allEvents ∧ DirectParent parent child := by
  obtain ⟨parent, hparent, hid⟩ :=
    hparents child hchild parentId hparentId
  exact ⟨parent, hparent, by simpa [DirectParent, hid] using hparentId⟩

end PSystem
