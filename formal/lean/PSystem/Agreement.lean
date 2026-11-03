import PSystem.Completeness

namespace PSystem

/-!
# Agreement of nodes (convergence plan, phases 5 and 6)

Main results:

- `derive_knowledge_invariant`: two nodes whose knowledge contains the same
  events, as sets, compute the same result: either the same state, or both
  reject the batch.
- `derive_perm_invariant`: the result does not depend on the order in which
  the events arrived (the rule in CLAUDE.md).

Hypotheses are only about the inputs: same events known, distinct ids in
each list (Python: `deduplicate_events`). There is no hypothesis about the
executions, about permutations between them, or about independence of
accounts; all of that is derived (phases 2-4).

These theorems supersede `P09_multi_node_convergence`,
`P13_independent_linearizations_are_deterministic` and
`R1_10_distributed_convergence`, which assumed the permutation.
-/

/-- `ValidSequence` only depends on which events are known. -/
theorem validSequence_congr {A B seq : List Event}
    (hk : ∀ e, e ∈ A ↔ e ∈ B) (h : ValidSequence A seq) :
    ValidSequence B seq := by
  induction h with
  | nil => exact ValidSequence.nil
  | append _ hevent hfresh hready ih =>
      exact ValidSequence.append ih ((hk _).1 hevent) hfresh hready

/-- If one node succeeds, a node with the same knowledge succeeds with the same state. -/
theorem derive_some_transfer
    (s : State) {A B : List Event} {t : State}
    (hk : ∀ e, e ∈ A ↔ e ∈ B)
    (hndA : (A.map Event.id).Nodup)
    (hndB : (B.map Event.id).Nodup)
    (hA : derive s A = some t) :
    derive s B = some t := by
  obtain ⟨seq, ⟨hperm, hvalid, hrun⟩, rfl⟩ := derive_sound s A t hndA hA
  have hAB : A.Perm B :=
    (List.perm_ext_iff_of_nodup (nodup_of_nodup_ids hndA)
      (nodup_of_nodup_ids hndB)).2 hk
  have hvalidB : ValidExecution s B seq :=
    ⟨hperm.trans hAB, validSequence_congr hk hvalid, hrun⟩
  obtain ⟨tB, htB⟩ := derive_complete s B hndB ⟨seq, hvalidB⟩
  rw [htB, derive_eq_valid_execution s hndB htB hvalidB]

/--
Two nodes that know the same events compute the same result: the same
state, or both reject.
-/
theorem derive_knowledge_invariant
    (s : State) {A B : List Event}
    (hk : ∀ e, e ∈ A ↔ e ∈ B)
    (hndA : (A.map Event.id).Nodup)
    (hndB : (B.map Event.id).Nodup) :
    derive s A = derive s B := by
  cases hA : derive s A with
  | some t => exact (derive_some_transfer s hk hndA hndB hA).symm
  | none =>
      cases hB : derive s B with
      | none => rfl
      | some t =>
          have := derive_some_transfer s (fun e => (hk e).symm) hndB hndA hB
          rw [hA] at this
          cases this

/-- The result does not depend on the order in which events arrived. -/
theorem derive_perm_invariant
    (s : State) {A B : List Event}
    (hperm : A.Perm B)
    (hnd : (A.map Event.id).Nodup) :
    derive s A = derive s B :=
  derive_knowledge_invariant s (fun _ => hperm.mem_iff) hnd
    ((hperm.map Event.id).nodup_iff.mp hnd)

end PSystem
