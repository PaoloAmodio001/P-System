import PSystem.Derive
import PSystem.R17OrderBridge

namespace PSystem

/-!
# State convergence for valid executions (convergence plan, phase 2)

Main results:

- `executable_runs_same_state`: two executable runs of the same events, in
  any two orders, reach the same state. Accounts may be shared and events
  may form causal chains; no independence hypothesis is used.
- `valid_executions_same_state`: the same for two valid executions of one
  event list.
- `equivalent_knowledge_same_state`: two nodes whose knowledge contains the
  same events (as sets) reach the same state with any valid execution of
  their own knowledge. The permutation between the two executions is
  derived, not assumed.

Method: along an executable run no subtraction is truncated, so for every
account `final + outflow = initial + inflow`, and the nonce advances by the
number of events sent. Inflow, outflow and counts do not depend on the
order of the events.

Executability is essential: `ApplyEvent` alone truncates at zero, and
without `ExecutableRun` the result is false (overdraft then refund differs
from refund then overdraft).
-/

/-! ## Order-independent sums -/

/-- Sum of `f` over a list of events. -/
def sumBy (f : Event → Nat) : List Event → Nat
  | [] => 0
  | e :: rest => f e + sumBy f rest

@[simp] theorem sumBy_nil (f : Event → Nat) : sumBy f [] = 0 := rfl

@[simp] theorem sumBy_cons (f : Event → Nat) (e : Event) (rest : List Event) :
    sumBy f (e :: rest) = f e + sumBy f rest := rfl

/-- `sumBy` does not depend on the order of the events. -/
theorem sumBy_perm (f : Event → Nat) {l₁ l₂ : List Event}
    (h : l₁.Perm l₂) : sumBy f l₁ = sumBy f l₂ := by
  induction h with
  | nil => rfl
  | cons e _ ih => simp [ih]
  | swap a b l => simp; omega
  | trans _ _ ih₁ ih₂ => exact ih₁.trans ih₂

/-- Total amount sent by `id`. -/
def outflow (id : Identity) : List Event → Nat :=
  sumBy (fun e => if e.sender = id then e.amount else 0)

/-- Total amount received by `id`. -/
def inflow (id : Identity) : List Event → Nat :=
  sumBy (fun e => if e.receiver = id then e.amount else 0)

/-- Number of events sent by `id`. -/
def sentCount (id : Identity) : List Event → Nat :=
  sumBy (fun e => if e.sender = id then 1 else 0)

/-! ## Closed form of an executable run -/

/-- The nonce of every account advances by the number of events it sent. -/
theorem nonce_closed_form (s : State) (seq : List Event) (id : Identity) :
    (ApplyEvents s seq).nonce id = s.nonce id + sentCount id seq := by
  induction seq generalizing s with
  | nil => simp [ApplyEvents, sentCount]
  | cons e rest ih =>
      have h := ih (ApplyEvent s e)
      simp only [ApplyEvents, sentCount, sumBy_cons] at h ⊢
      rw [h]
      by_cases hs : id = e.sender
      · subst hs
        simp [ApplyEvent]
        exact Nat.add_assoc _ _ _
      · have hs' : ¬ e.sender = id := fun h => hs h.symm
        simp [ApplyEvent, hs, hs']

/--
Along an executable run, for every account:
`final balance + outflow = initial balance + inflow`.
No subtraction is truncated because every step is executable.
-/
theorem balance_closed_form (s : State) (seq : List Event)
    (hrun : ExecutableRun s seq) (id : Identity) :
    (ApplyEvents s seq).balance id + outflow id seq =
      s.balance id + inflow id seq := by
  induction seq generalizing s with
  | nil => simp [ApplyEvents, outflow, inflow]
  | cons e rest ih =>
      obtain ⟨hexec, hrest⟩ := hrun
      obtain ⟨_, hne, hbal, _⟩ := hexec
      have h := ih (ApplyEvent s e) hrest
      simp only [ApplyEvents, outflow, inflow, sumBy_cons] at h ⊢
      by_cases hs : id = e.sender
      · subst hs
        have hr : ¬ e.receiver = e.sender := fun h => hne h.symm
        simp [ApplyEvent, hr] at h ⊢
        omega
      · have hs' : ¬ e.sender = id := fun h => hs h.symm
        by_cases hr : id = e.receiver
        · subst hr
          simp [ApplyEvent, hs, hs'] at h ⊢
          omega
        · have hr' : ¬ e.receiver = id := fun h => hr h.symm
          simp [ApplyEvent, hs, hs', hr, hr'] at h ⊢
          omega

/-! ## Convergence -/

/--
Two executable runs of the same events, in any two orders, reach the same
state. No independence between events is assumed: accounts may be shared
and the runs may interleave causal chains differently.
-/
theorem executable_runs_same_state
    (s : State) {seq₁ seq₂ : List Event}
    (hperm : seq₁.Perm seq₂)
    (hrun₁ : ExecutableRun s seq₁)
    (hrun₂ : ExecutableRun s seq₂) :
    ApplyEvents s seq₁ = ApplyEvents s seq₂ := by
  apply state_eq_of_fields_eq
  · funext id
    have h₁ := balance_closed_form s seq₁ hrun₁ id
    have h₂ := balance_closed_form s seq₂ hrun₂ id
    have hout : outflow id seq₁ = outflow id seq₂ := sumBy_perm _ hperm
    have hin : inflow id seq₁ = inflow id seq₂ := sumBy_perm _ hperm
    omega
  · funext id
    rw [nonce_closed_form, nonce_closed_form]
    have hcount : sentCount id seq₁ = sentCount id seq₂ := sumBy_perm _ hperm
    rw [hcount]

/-- Two valid executions of the same event list reach the same state. -/
theorem valid_executions_same_state
    (s : State) {events seq₁ seq₂ : List Event}
    (h₁ : ValidExecution s events seq₁)
    (h₂ : ValidExecution s events seq₂) :
    ApplyEvents s seq₁ = ApplyEvents s seq₂ :=
  executable_runs_same_state s (h₁.1.trans h₂.1.symm) h₁.2.2 h₂.2.2

/-- The events of a valid sequence are pairwise distinct. -/
theorem valid_sequence_nodup {events seq : List Event}
    (h : ValidSequence events seq) : seq.Nodup :=
  List.Pairwise.of_map Event.id (fun _ _ hne heq => hne (heq ▸ rfl))
    (r17_valid_sequence_ids_nodup events seq h)

/--
Two nodes whose knowledge contains the same events, as sets, reach the same
state with any valid execution of their own knowledge.

The hypotheses are only about the inputs (same events known) and about
each node running some valid execution. That the two executions are
permutations of each other is derived, not assumed; duplicates in the
knowledge lists are excluded by validity, not by hypothesis.
-/
theorem equivalent_knowledge_same_state
    (s : State) {knowledgeA knowledgeB seqA seqB : List Event}
    (hknowledge : ∀ e, e ∈ knowledgeA ↔ e ∈ knowledgeB)
    (hA : ValidExecution s knowledgeA seqA)
    (hB : ValidExecution s knowledgeB seqB) :
    ApplyEvents s seqA = ApplyEvents s seqB := by
  have hnodupA : knowledgeA.Nodup := hA.1.nodup_iff.mp (valid_sequence_nodup hA.2.1)
  have hnodupB : knowledgeB.Nodup := hB.1.nodup_iff.mp (valid_sequence_nodup hB.2.1)
  have hAB : knowledgeA.Perm knowledgeB :=
    (List.perm_ext_iff_of_nodup hnodupA hnodupB).2 hknowledge
  exact executable_runs_same_state s (hA.1.trans (hAB.trans hB.1.symm))
    hA.2.2 hB.2.2

end PSystem
