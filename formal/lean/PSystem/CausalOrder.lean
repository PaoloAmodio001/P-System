import PSystem.Basic

namespace PSystem

/-!
# Causal readiness and valid sequences

The causal part of the model used by `derive` and its proofs. Taken from
the former R17 modules (see the tag `pre-lean-cleanup`); only the
definitions and lemmas used by the convergence results are kept.

Causality is expressed through ids that have already been processed
(`R17Ready`), so no global acyclicity or closure hypothesis is needed.
-/

/-- An event is ready when every declared parent id has been processed. -/
def R17Ready (processed : List EventId) (event : Event) : Prop :=
  ∀ parentId, parentId ∈ event.parents → parentId ∈ processed

/-- Boolean version of `R17Ready`, used by the executable model. -/
def r17ReadyBool (processed : List EventId) (event : Event) : Bool :=
  event.parents.all (fun parentId => processed.contains parentId)

theorem r17ReadyBool_iff_R17Ready (processed : List EventId) (event : Event) :
    r17ReadyBool processed event = true ↔ R17Ready processed event := by
  simp [r17ReadyBool, R17Ready, List.all_eq_true]

/--
A sequence built by appending known events with fresh ids, each ready with
respect to the ids before it.
-/
inductive ValidSequence (allEvents : List Event) : List Event → Prop
  | nil : ValidSequence allEvents []
  | append
      {processed : List Event}
      {event : Event}
      (hprev : ValidSequence allEvents processed)
      (hevent : event ∈ allEvents)
      (hfresh : ∀ old, old ∈ processed → old.id ≠ event.id)
      (hready : R17Ready (processed.map Event.id) event) :
      ValidSequence allEvents (processed ++ [event])

/-- The ids of a valid sequence are pairwise distinct. -/
theorem r17_valid_sequence_ids_nodup
    (allEvents ordered : List Event)
    (hseq : ValidSequence allEvents ordered) :
    (ordered.map Event.id).Nodup := by
  induction hseq with
  | nil => simp
  | @append processed event hprev hevent hfresh hready ih =>
      simp only [List.map_append, List.map_singleton]
      apply List.nodup_append.mpr
      refine ⟨ih, by simp, ?_⟩
      intro id hid id' hsingle
      simp only [List.mem_singleton] at hsingle
      obtain ⟨old, hold, holdId⟩ := List.mem_map.mp hid
      intro heq
      exact (hfresh old hold) (holdId.trans (heq.trans hsingle))

/-- Filtering out an element that is rejected makes a list strictly shorter. -/
theorem r17_filter_length_lt_of_rejected
    {α : Type} (items : List α) (keep : α → Bool)
    (x : α) (hx : x ∈ items) (hrejected : keep x = false) :
    (items.filter keep).length < items.length := by
  apply Nat.lt_of_le_of_ne (List.length_filter_le keep items)
  intro heq
  have hall : ∀ a, a ∈ items → keep a = true :=
    (List.length_filter_eq_length_iff).1 heq
  exact Bool.noConfusion (hall x hx |>.symm.trans hrejected)

theorem r17_filter_selected_length_lt
    (remaining : List Event)
    (selected : Event)
    (hselected : selected ∈ remaining) :
    (remaining.filter (fun event => event.id != selected.id)).length <
      remaining.length := by
  apply r17_filter_length_lt_of_rejected
    remaining (fun event => event.id != selected.id) selected hselected
  simp

end PSystem
