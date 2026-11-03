import PSystem.Convergence

namespace PSystem

/-!
# Soundness of `derive` (convergence plan, phase 3)

Main results:

- `derive_sound`: if `derive s events = some t`, then `t` is the state of a
  valid execution of `events` (every event exactly once, parents before
  children, every step executable).
- `derive_agrees`: two nodes that know the same events and whose
  derivations both succeed obtain the same state (with phase 2).

Hypothesis on the input: event ids are distinct, `(events.map Event.id).Nodup`.
Python enforces the same precondition: `deduplicate_events` removes copies and
`ConflictResolver.compatible` rejects one id with two payloads. The model
removes every event with the selected id (`dropId`), so without this
hypothesis a duplicated event would run once and the run would not be a
permutation of the input.

Not proved here: that `derive` succeeds whenever a valid execution exists
(phase 4).
-/

/-! ## Unique ids -/

theorem ids_inj {l : List Event} (hnd : (l.map Event.id).Nodup)
    {a b : Event} (ha : a ∈ l) (hb : b ∈ l) (hab : a.id = b.id) : a = b := by
  induction l with
  | nil => simp at ha
  | cons x xs ih =>
      simp only [List.map_cons, List.nodup_cons] at hnd
      obtain ⟨hx, hxs⟩ := hnd
      simp only [List.mem_cons] at ha hb
      rcases ha with rfl | ha <;> rcases hb with rfl | hb
      · rfl
      · exact False.elim (hx (hab ▸ List.mem_map.mpr ⟨b, hb, rfl⟩))
      · exact False.elim (hx (hab ▸ List.mem_map.mpr ⟨a, ha, rfl⟩))
      · exact ih hxs ha hb

theorem nodup_of_nodup_ids {l : List Event} (hnd : (l.map Event.id).Nodup) :
    l.Nodup :=
  List.Pairwise.of_map Event.id (fun _ _ hne heq => hne (heq ▸ rfl)) hnd

theorem dropId_nodup_ids {l : List Event} (id : EventId)
    (hnd : (l.map Event.id).Nodup) : ((dropId id l).map Event.id).Nodup :=
  hnd.sublist (List.filter_sublist.map Event.id)

theorem mem_dropId {l : List Event} {id : EventId} {a : Event} :
    a ∈ dropId id l ↔ a ∈ l ∧ a.id ≠ id := by
  simp [dropId]

/-- With unique ids, removing the selected event leaves the rest. -/
theorem perm_cons_dropId {l : List Event} {e : Event}
    (hnd : (l.map Event.id).Nodup) (he : e ∈ l) :
    l.Perm (e :: dropId e.id l) := by
  have hl := nodup_of_nodup_ids hnd
  have hr : (e :: dropId e.id l).Nodup := by
    refine List.nodup_cons.mpr ⟨?_, nodup_of_nodup_ids (dropId_nodup_ids e.id hnd)⟩
    intro hmem
    exact (mem_dropId.mp hmem).2 rfl
  refine (List.perm_ext_iff_of_nodup hl hr).2 ?_
  intro a
  simp only [List.mem_cons, mem_dropId]
  constructor
  · intro ha
    by_cases hid : a.id = e.id
    · exact Or.inl (ids_inj hnd ha he hid)
    · exact Or.inr ⟨ha, hid⟩
  · rintro (rfl | ⟨ha, _⟩)
    · exact he
    · exact ha

/-! ## Readiness along a run (cons form) -/

/-- Every event is causally ready when it runs, given the ids already processed. -/
def ReadyRun : List EventId → List Event → Prop
  | _, [] => True
  | processed, e :: rest => R17Ready processed e ∧ ReadyRun (processed ++ [e.id]) rest

/-- Bridge from the cons-form run to R17's `ValidSequence` (snoc form). -/
theorem validSequence_of_readyRun
    (events : List Event) :
    ∀ (pre rest : List Event),
      ValidSequence events pre →
      ReadyRun (pre.map Event.id) rest →
      ((pre ++ rest).map Event.id).Nodup →
      (∀ e, e ∈ rest → e ∈ events) →
      ValidSequence events (pre ++ rest)
  | pre, [], hpre, _, _, _ => by simpa using hpre
  | pre, e :: rest, hpre, hready, hnd, hmem => by
      obtain ⟨hreadyE, hreadyRest⟩ := hready
      have hfresh : ∀ old, old ∈ pre → old.id ≠ e.id := by
        intro old hold heq
        have hsplit : ((pre ++ e :: rest).map Event.id) =
            pre.map Event.id ++ e.id :: rest.map Event.id := by simp
        rw [hsplit] at hnd
        have hdisj := (List.nodup_append.mp hnd).2.2
        exact hdisj old.id (List.mem_map.mpr ⟨old, hold, rfl⟩) e.id (by simp) heq
      have hnext : ValidSequence events (pre ++ [e]) :=
        ValidSequence.append hpre (hmem e (by simp)) hfresh hreadyE
      have hreadyNext : ReadyRun ((pre ++ [e]).map Event.id) rest := by
        simpa using hreadyRest
      have hndNext : (((pre ++ [e]) ++ rest).map Event.id).Nodup := by
        simpa using hnd
      have h := validSequence_of_readyRun events (pre ++ [e]) rest hnext
        hreadyNext hndNext (fun x hx => hmem x (by simp [hx]))
      simpa using h

/-! ## Soundness of the loop -/

/--
Invariant of `executionOrder`: the returned order is a permutation of the
remaining events, every step is executable, and every event is ready when
it runs.
-/
theorem executionOrder_sound
    (s : State) (processed : List EventId) (remaining seq : List Event)
    (hnd : (remaining.map Event.id).Nodup)
    (h : executionOrder s processed remaining = some seq) :
    seq.Perm remaining ∧ ExecutableRun s seq ∧ ReadyRun processed seq := by
  rw [executionOrder] at h
  split at h
  · rename_i hnil
    cases h
    subst hnil
    exact ⟨List.Perm.refl _, trivial, trivial⟩
  · split at h
    · cases h
    · rename_i e hsel
      obtain ⟨rest, hrest, rfl⟩ := Option.map_eq_some_iff.mp h
      obtain ⟨hmem, hready, hexec, _⟩ := selectNext_spec hsel
      have hlt : (dropId e.id remaining).length < remaining.length :=
        dropId_length_lt hmem
      have ih := executionOrder_sound (ApplyEvent s e) (processed ++ [e.id])
        (dropId e.id remaining) rest (dropId_nodup_ids e.id hnd) hrest
      refine ⟨?_, ⟨hexec, ih.2.1⟩, ⟨hready, ih.2.2⟩⟩
      exact ((ih.1.cons e).trans (perm_cons_dropId hnd hmem).symm)
termination_by remaining.length

/-! ## Soundness of `derive` -/

/--
If `derive` returns a state, that state is produced by a valid execution
of the input events.
-/
theorem derive_sound
    (s : State) (events : List Event) (t : State)
    (hnd : (events.map Event.id).Nodup)
    (h : derive s events = some t) :
    ∃ seq, ValidExecution s events seq ∧ ApplyEvents s seq = t := by
  obtain ⟨seq, hord, rfl⟩ := Option.map_eq_some_iff.mp h
  obtain ⟨hperm, hexec, hready⟩ := executionOrder_sound s [] events seq hnd hord
  refine ⟨seq, ⟨hperm, ?_, hexec⟩, rfl⟩
  have hndSeq : (seq.map Event.id).Nodup :=
    (hperm.map Event.id).nodup_iff.mpr hnd
  simpa using validSequence_of_readyRun events [] seq ValidSequence.nil
    (by simpa using hready) (by simpa using hndSeq)
    (fun e he => hperm.mem_iff.mp he)

/--
The state returned by `derive` equals the state of every valid execution
of the same events.
-/
theorem derive_eq_valid_execution
    (s : State) {events seq : List Event} {t : State}
    (hnd : (events.map Event.id).Nodup)
    (h : derive s events = some t)
    (hvalid : ValidExecution s events seq) :
    t = ApplyEvents s seq := by
  obtain ⟨seq', hvalid', rfl⟩ := derive_sound s events t hnd h
  exact valid_executions_same_state s hvalid' hvalid

/--
Two nodes that know the same events, and whose derivations both succeed,
obtain the same state. The input lists may be in any order.
-/
theorem derive_agrees
    (s : State) {knowledgeA knowledgeB : List Event} {tA tB : State}
    (hknowledge : ∀ e, e ∈ knowledgeA ↔ e ∈ knowledgeB)
    (hndA : (knowledgeA.map Event.id).Nodup)
    (hndB : (knowledgeB.map Event.id).Nodup)
    (hA : derive s knowledgeA = some tA)
    (hB : derive s knowledgeB = some tB) :
    tA = tB := by
  obtain ⟨seqA, hvalidA, rfl⟩ := derive_sound s knowledgeA tA hndA hA
  obtain ⟨seqB, hvalidB, rfl⟩ := derive_sound s knowledgeB tB hndB hB
  exact equivalent_knowledge_same_state s hknowledge hvalidA hvalidB

end PSystem
