import PSystem.QuorumSafety

namespace PSystem.Quorum

/-!
# A first result on liveness, with delivery as a hypothesis

`honest_sender_certifies`: if a sender signs one version of an event, and `q` honest validators
receive it and no conflicting request passes their own check, then each of them votes for it and
their signatures form a valid certificate. `certificate_executes` says that an honest node that
receives it, on a state where the event can run, executes it.

This is not unconditional liveness. Delivery is a hypothesis: nothing here says that a network
delivers. With fair delivery to `2f+1` honest validators it gives what an honest sender needs.
The hypothesis `NoConflict` is what a sender that signs two versions can break.
It needs no bound on faulty validators: they can only fail to help.
-/

/-- No other request that passes `auth` conflicts with `e`, in `(sender, nonce)` or in id. -/
def NoConflict {n : Nat} {Sig : Type} (auth : Event → Bool) (inputs : List (Input n Sig))
    (e : Event) : Prop :=
  ∀ e', Input.voteRequest e' ∈ inputs → auth e' = true →
    e' = e ∨ (¬ (e'.sender = e.sender ∧ e'.nonce = e.nonce) ∧ e'.id ≠ e.id)

/-- `voteAllowed` holds when every earlier vote is `e` or unrelated to it. -/
theorem voteAllowed_of_free {votes : List Event} {e : Event}
    (h : ∀ v, v ∈ votes → v = e ∨ (¬ (v.sender = e.sender ∧ v.nonce = e.nonce) ∧ v.id ≠ e.id)) :
    voteAllowed votes e = true := by
  refine List.all_eq_true.mpr fun v hv => ?_
  rcases h v hv with rfl | ⟨hkey, hid⟩
  · simp
  · have hkey' : (v.sender == e.sender && v.nonce == e.nonce) = false := by
      cases hs : v.sender == e.sender <;> cases hn : v.nonce == e.nonce <;> simp_all
    simp [hkey', hid]

theorem votes_free_foldl {n : Nat} {Sig : Type} (verify : Fin n → Event → Sig → Bool) (q : Nat)
    (auth : Event → Bool) (e : Event) (inputs : List (Input n Sig)) (st : NodeState n Sig)
    (hfree : ∀ v, v ∈ st.votes → v = e ∨ (¬ (v.sender = e.sender ∧ v.nonce = e.nonce) ∧ v.id ≠ e.id))
    (hinputs : NoConflict auth inputs e) :
    (∀ v, v ∈ (inputs.foldl (step verify q auth) st).votes →
      v = e ∨ (¬ (v.sender = e.sender ∧ v.nonce = e.nonce) ∧ v.id ≠ e.id)) ∧
    (e ∈ st.votes ∨ (Input.voteRequest e ∈ inputs ∧ auth e = true) →
      e ∈ (inputs.foldl (step verify q auth) st).votes) := by
  induction inputs generalizing st with
  | nil =>
      refine ⟨hfree, ?_⟩
      rintro (h | ⟨h, _⟩)
      · exact h
      · simp at h
  | cons i rest ih =>
      have hrest : NoConflict auth rest e := fun e' he' ha =>
        hinputs e' (List.mem_cons_of_mem i he') ha
      have hnext : ∀ v, v ∈ (step verify q auth st i).votes →
          v = e ∨ (¬ (v.sender = e.sender ∧ v.nonce = e.nonce) ∧ v.id ≠ e.id) := by
        intro v hv
        cases i with
        | certificate c =>
            simp only [step] at hv
            split at hv <;> exact hfree v hv
        | voteRequest e' =>
            simp only [step] at hv
            split at hv
            · rename_i hif
              rcases List.mem_cons.mp hv with rfl | hold
              · exact hinputs v List.mem_cons_self (Bool.and_eq_true_iff.mp hif).1
              · exact hfree v hold
            · exact hfree v hv
      obtain ⟨h₁, h₂⟩ := ih (step verify q auth st i) hnext hrest
      refine ⟨h₁, ?_⟩
      intro hgoal
      apply h₂
      cases i with
      | certificate c =>
          rcases hgoal with hmem | ⟨hin, hauth⟩
          · left
            simp only [step]
            split <;> exact hmem
          · have : Input.voteRequest e ∈ rest := by simpa using hin
            exact Or.inr ⟨this, hauth⟩
      | voteRequest e' =>
          rcases hgoal with hmem | ⟨hin, hauth⟩
          · left
            simp only [step]
            split
            · exact List.mem_cons_of_mem _ hmem
            · exact hmem
          · rcases List.mem_cons.mp hin with heq | hin'
            · cases heq
              left
              have hallowed := voteAllowed_of_free hfree
              simp [step, hauth, hallowed]
            · exact Or.inr ⟨hin', hauth⟩

/-- An honest validator that receives `e`, with no conflict among its inputs, votes for it. -/
theorem votes_for_delivered {n : Nat} {Sig : Type} (verify : Fin n → Event → Sig → Bool) (q : Nat)
    (auth : Event → Bool) (s₀ : State) (inputs : List (Input n Sig)) (e : Event)
    (hdelivered : Input.voteRequest e ∈ inputs) (hauth : auth e = true)
    (hconflict : NoConflict auth inputs e) :
    e ∈ (runNode verify q auth s₀ inputs).votes :=
  (votes_free_foldl verify q auth e inputs _ (by intro v hv; simp at hv) hconflict).2
    (Or.inr ⟨hdelivered, hauth⟩)

/--
Liveness, given delivery. `q` honest validators receive one version of an event, and none of them
sees a conflicting request that passes its check. Then each votes for it, and their signatures
form a valid certificate. `sign` is the signature each of them produces when it votes.
-/
theorem honest_sender_certifies {n q : Nat} {Sig : Type}
    (verify : Fin n → Event → Sig → Bool) (auth : Fin n → Event → Bool) (s₀ : State)
    (inputs : Fin n → List (Input n Sig)) (e : Event)
    (honest : List (Fin n)) (hnd : honest.Nodup) (hq : q ≤ honest.length)
    (sign : Fin n → Sig) (hsign : ∀ x, x ∈ honest → verify x e (sign x) = true)
    (hdelivered : ∀ x, x ∈ honest → Input.voteRequest e ∈ inputs x)
    (hauth : ∀ x, x ∈ honest → auth x e = true)
    (hconflict : ∀ x, x ∈ honest → NoConflict (auth x) (inputs x) e) :
    (∀ x, x ∈ honest → e ∈ (runNode verify q (auth x) s₀ (inputs x)).votes) ∧
    certValid verify q ⟨e, honest.map fun x => (x, sign x)⟩ = true := by
  refine ⟨fun x hx => votes_for_delivered verify q (auth x) s₀ (inputs x) e
    (hdelivered x hx) (hauth x hx) (hconflict x hx), ?_⟩
  simp only [certValid, Bool.and_eq_true, decide_eq_true_eq]
  refine ⟨⟨?_, ?_⟩, ?_⟩
  · simpa [List.map_map, Function.comp_def] using hnd
  · simpa using hq
  · refine List.all_eq_true.mpr fun p hp => ?_
    obtain ⟨x, hx, rfl⟩ := List.mem_map.mp hp
    exact hsign x hx

/-- A valid certificate for an event that can run now is executed. -/
theorem certificate_executes {n : Nat} {Sig : Type} (verify : Fin n → Event → Sig → Bool)
    (q : Nat) (auth : Event → Bool) (st : NodeState n Sig) (c : Cert n Sig)
    (hvalid : certValid verify q c = true)
    (hexec : executableBool st.state c.event = true)
    (hready : r17ReadyBool (st.executed.map Event.id) c.event = true)
    (hfresh : (st.executed.map Event.id).contains c.event.id = false) :
    c.event ∈ (step verify q auth st (.certificate c)).executed := by
  have hcond : (certValid verify q c && executableBool st.state c.event &&
      r17ReadyBool (st.executed.map Event.id) c.event &&
      !(st.executed.map Event.id).contains c.event.id) = true := by
    simp only [hvalid, hexec, hready, hfresh]
    rfl
  simp only [step]
  rw [if_pos hcond]
  simp [NodeState.executed]

end PSystem.Quorum
