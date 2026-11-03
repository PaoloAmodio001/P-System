import PSystem.Agreement
import PSystem.Quorum

namespace PSystem.Quorum

/-!
# The state of a node is what `derive` computes (obligation O7)

Main results:

- `state_is_derive`: for any inputs, `derive` applied to the events a node
  executed succeeds and returns the node's state. Nothing is assumed about
  quorums, faults or signatures: this is a property of the execution rule.
- `same_executed_same_state`: two nodes that executed the same events, as sets,
  are in the same state, even in different orders. This brings
  `derive_knowledge_invariant` to the quorum model.

Neither says that nodes execute the same events. That needs delivery and the
quorum hypotheses, and it is `convergence_after_exchange`, still open.

Method: the log only grows at the end, like `ValidSequence`, and each execution
checks what the next step of a valid execution requires.
-/

/-- What holds of a node's executed events after any inputs. -/
structure LogInvariant {n : Nat} {Sig : Type} (s₀ : State) (st : NodeState n Sig) : Prop where
  run : ExecutableRun s₀ st.executed
  state : ApplyEvents s₀ st.executed = st.state
  valid : ∀ K : List Event, (∀ e, e ∈ st.executed → e ∈ K) → ValidSequence K st.executed

theorem logInvariant_step {n : Nat} {Sig : Type} (verify : Fin n → Event → Sig → Bool) (q : Nat)
    (auth : Event → Bool) (s₀ : State) (st : NodeState n Sig) (i : Input n Sig)
    (h : LogInvariant s₀ st) : LogInvariant s₀ (step verify q auth st i) := by
  cases i with
  | voteRequest e =>
      simp only [step]
      split
      · exact ⟨h.run, h.state, h.valid⟩
      · exact h
  | certificate c =>
      simp only [step]
      split
      · rename_i hif
        simp only [Bool.and_eq_true, Bool.not_eq_true', List.contains_eq_mem,
          decide_eq_false_iff_not] at hif
        obtain ⟨⟨⟨_, hexec⟩, hready⟩, hfresh⟩ := hif
        have hexecuted : (st.log ++ [c]).map Cert.event = st.executed ++ [c.event] := by
          simp [NodeState.executed]
        constructor
        · show ExecutableRun s₀ ((st.log ++ [c]).map Cert.event)
          rw [hexecuted, executableRun_append, h.state]
          exact ⟨h.run, (executableBool_iff _ _).1 hexec, trivial⟩
        · show ApplyEvents s₀ ((st.log ++ [c]).map Cert.event) = ApplyEvent st.state c.event
          rw [hexecuted, apply_events_append, h.state]
          rfl
        · intro K hK
          show ValidSequence K ((st.log ++ [c]).map Cert.event)
          rw [hexecuted]
          have hK' : ∀ e, e ∈ st.executed ++ [c.event] → e ∈ K := fun e he =>
            hK e (by
              show e ∈ (st.log ++ [c]).map Cert.event
              rw [hexecuted]
              exact he)
          exact ValidSequence.append
            (h.valid K fun e he => hK' e (List.mem_append_left _ he))
            (hK' _ (List.mem_append_right _ List.mem_cons_self))
            (fun old hold hid => hfresh (hid ▸ List.mem_map_of_mem hold))
            ((r17ReadyBool_iff_R17Ready _ _).1 hready)
      · exact h

theorem logInvariant_foldl {n : Nat} {Sig : Type} (verify : Fin n → Event → Sig → Bool) (q : Nat)
    (auth : Event → Bool) (s₀ : State) (inputs : List (Input n Sig)) (st : NodeState n Sig)
    (h : LogInvariant s₀ st) :
    LogInvariant s₀ (inputs.foldl (step verify q auth) st) := by
  induction inputs generalizing st with
  | nil => exact h
  | cons i rest ih => exact ih _ (logInvariant_step verify q auth s₀ st i h)

/-- The invariant holds for a node after any inputs. -/
theorem logInvariant_runNode {n : Nat} {Sig : Type} (verify : Fin n → Event → Sig → Bool)
    (q : Nat) (auth : Event → Bool) (s₀ : State) (inputs : List (Input n Sig)) :
    LogInvariant s₀ (runNode verify q auth s₀ inputs) :=
  logInvariant_foldl verify q auth s₀ inputs _
    ⟨trivial, rfl, fun _ _ => ValidSequence.nil⟩

/-- The executed events of a node are a valid execution of themselves. -/
theorem executed_valid {n : Nat} {Sig : Type} (verify : Fin n → Event → Sig → Bool) (q : Nat)
    (auth : Event → Bool) (s₀ : State) (inputs : List (Input n Sig)) :
    ValidExecution s₀ (runNode verify q auth s₀ inputs).executed
      (runNode verify q auth s₀ inputs).executed :=
  have h := logInvariant_runNode verify q auth s₀ inputs
  ⟨List.Perm.refl _, h.valid _ fun _ he => he, h.run⟩

/-- A node never executes two events with the same id. -/
theorem executed_ids_nodup {n : Nat} {Sig : Type} (verify : Fin n → Event → Sig → Bool) (q : Nat)
    (auth : Event → Bool) (s₀ : State) (inputs : List (Input n Sig)) :
    ((runNode verify q auth s₀ inputs).executed.map Event.id).Nodup :=
  r17_valid_sequence_ids_nodup _ _ (executed_valid verify q auth s₀ inputs).2.1

/--
A node's state is what `derive` computes from the events it executed, for any
inputs. So every event a node executes can enter `derive`, and the derivation
does not reject the batch.
-/
theorem state_is_derive
    {n : Nat} {Sig : Type} (verify : Fin n → Event → Sig → Bool) (q : Nat)
    (auth : Event → Bool) (s₀ : State) (inputs : List (Input n Sig)) :
    derive s₀ (runNode verify q auth s₀ inputs).executed
      = some (runNode verify q auth s₀ inputs).state := by
  have hvalid := executed_valid verify q auth s₀ inputs
  have hnd := executed_ids_nodup verify q auth s₀ inputs
  obtain ⟨t, ht⟩ := derive_complete s₀ _ hnd ⟨_, hvalid⟩
  rw [ht, derive_eq_valid_execution s₀ hnd ht hvalid,
    (logInvariant_runNode verify q auth s₀ inputs).state]

/--
Two nodes that executed the same events, as sets and from the same initial
state, are in the same state, even if they executed them in different orders.
They may have different `q`, `verify`, `auth` and inputs.
-/
theorem same_executed_same_state
    {n : Nat} {Sig : Type} (verify₁ verify₂ : Fin n → Event → Sig → Bool) (q₁ q₂ : Nat)
    (auth₁ auth₂ : Event → Bool) (s₀ : State) (inputs₁ inputs₂ : List (Input n Sig))
    (hsame : ∀ e, e ∈ (runNode verify₁ q₁ auth₁ s₀ inputs₁).executed ↔
      e ∈ (runNode verify₂ q₂ auth₂ s₀ inputs₂).executed) :
    (runNode verify₁ q₁ auth₁ s₀ inputs₁).state = (runNode verify₂ q₂ auth₂ s₀ inputs₂).state := by
  have h := derive_knowledge_invariant s₀ hsame
    (executed_ids_nodup verify₁ q₁ auth₁ s₀ inputs₁)
    (executed_ids_nodup verify₂ q₂ auth₂ s₀ inputs₂)
  rw [state_is_derive, state_is_derive] at h
  exact Option.some.inj h

end PSystem.Quorum
