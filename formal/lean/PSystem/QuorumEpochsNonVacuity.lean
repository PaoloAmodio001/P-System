import PSystem.QuorumNonVacuity
import PSystem.QuorumEpochs

namespace PSystem.QuorumExamples

/-!
# The results on thresholds and epochs are not vacuous

Concrete witnesses, as in `QuorumNonVacuity`. Computations on one instance each, whose job is
to show that the hypotheses can hold together and that dropping the locks gives a fork.

- `chain_satisfies_hypotheses`: a chain where `a` has a certificate in epoch 0, is carried as
  a lock, gets a new certificate in epoch 1, and `b` gets no vote there.
- `fork_without_carrying_locks`: if epoch 1 starts with no locks, `b` is certified there, and
  the two epochs hold certificates for two versions of one spend.
- `equivocation_run_6_satisfies_hypotheses`: `no_double_spend_q` with `n = 6`, `q = 5`.
- `unlock_safe_witness`: the hypotheses of `unlock_safe_5f1` hold with `f = 1`.
-/

open PSystem PSystem.Quorum
open PSystem.DeriveExamples (initial ev)

/-! ## Epochs -/

def votesForA : Fin 4 → List EpochInput
  | 0 => []
  | _ => [.voteRequest a, .close]

def tryBThenA : Fin 4 → List EpochInput
  | 0 => []
  | _ => [.voteRequest b, .voteRequest a, .close]

def epochOf (inputs : Fin 4 → List EpochInput) : Epoch where
  n := 4
  q := 3
  faulty := [0]
  auth := fun _ _ => true
  inputs := inputs
  reporters := [1, 2, 3]
  safe := by decide
  reportersNodup := by decide
  reportersQuorum := by decide

def chain : Nat → Epoch
  | 0 => epochOf votesForA
  | _ + 1 => epochOf tryBThenA

def chainLocks : Nat → List Event
  | 0 => []
  | _ + 1 => [a]

theorem chain_valid : ChainValid chain chainLocks := by
  intro k
  have hr : ∀ x : Fin 4, x ∈ ([1, 2, 3] : List (Fin 4)) →
      EpochInput.close ∈ votesForA x ∧ EpochInput.close ∈ tryBThenA x ∧
      (∀ e, e ∈ reportOf [] (fun _ => true) (votesForA x) → e = a) ∧
      (∀ e, e ∈ reportOf [a] (fun _ => true) (tryBThenA x) → e = a) := by
    intro x hx
    simp only [List.mem_cons, List.not_mem_nil, or_false] at hx
    rcases hx with rfl | rfl | rfl <;>
      refine ⟨by decide, by decide, ?_, ?_⟩ <;>
      · intro e he
        have hvotes : ∀ {l : List Event}, l = [a] → e ∈ l → e = a := by
          intro l hl hel
          subst hl
          simpa using hel
        exact hvotes (by decide +kernel) he
  cases k with
  | zero =>
      refine ⟨fun e he => by simp [chainLocks] at he, ?_⟩
      intro x hx _
      obtain ⟨h₁, _, h₃, _⟩ := hr x hx
      exact ⟨h₁, fun e he => by simp [chainLocks, h₃ e he]⟩
  | succ k =>
      refine ⟨fun e he => by simpa [chainLocks] using he, ?_⟩
      intro x hx _
      obtain ⟨_, h₂, _, h₄⟩ := hr x hx
      exact ⟨h₂, fun e he => by simp [chainLocks, h₄ e he]⟩

theorem mem_reporters : ∀ x : Fin 4, x ∈ ([1, 2, 3] : List (Fin 4)) → x = 1 ∨ x = 2 ∨ x = 3 := by
  decide

theorem certified_of {inputs : Fin 4 → List EpochInput} {locks : List Event} {e : Event}
    (h : ∀ x : Fin 4, x = 1 ∨ x = 2 ∨ x = 3 → e ∈ (runEpoch locks (fun _ => true) (inputs x)).votes) :
    Certified (epochOf inputs) locks e := by
  have hnd : ([1, 2, 3] : List (Fin 4)).Nodup := by decide
  exact ⟨([1, 2, 3] : List (Fin 4)), hnd, Nat.le_refl 3, fun x hx _ => h x (mem_reporters x hx)⟩

theorem certified_a_epoch_0 : Certified (chain 0) (chainLocks 0) a :=
  certified_of (inputs := votesForA) (locks := []) (e := a) (by
    intro x hx
    rcases hx with rfl | rfl | rfl <;> decide +kernel)

theorem certified_a_epoch_1 : Certified (chain 1) (chainLocks 1) a :=
  certified_of (inputs := tryBThenA) (locks := [a]) (e := a) (by
    intro x hx
    rcases hx with rfl | rfl | rfl <;> decide +kernel)

/--
Non-vacuity. The chain is valid, the same event has a certificate in both epochs, so an honest
sender with an unfinished event can finish it later. The other version of the spend gets no
certificate in epoch 1, and honest validators did not even vote for it.
-/
theorem chain_satisfies_hypotheses :
    ChainValid chain chainLocks ∧
    Certified (chain 0) (chainLocks 0) a ∧
    Certified (chain 1) (chainLocks 1) a ∧
    ¬ Certified (chain 1) (chainLocks 1) b ∧
    b ∉ (runEpoch [a] (fun _ => true) (tryBThenA 1)).votes := by
  refine ⟨chain_valid, certified_a_epoch_0, certified_a_epoch_1, ?_, by decide +kernel⟩
  intro hb
  have heq := no_double_spend_across_epochs chain_valid certified_a_epoch_0 hb
    a_b_conflict.1 a_b_conflict.2.1
  exact a_b_conflict.2.2 heq

/-- Without carrying the locks, epoch 1 certifies the other version of a spend certified in
epoch 0. So the rule on locks is needed by `no_double_spend_across_epochs`. -/
theorem fork_without_carrying_locks :
    Certified (chain 0) [] a ∧ Certified (chain 1) [] b ∧
    a.sender = b.sender ∧ a.nonce = b.nonce ∧ a ≠ b := by
  refine ⟨certified_a_epoch_0, ?_, a_b_conflict.1, a_b_conflict.2.1, a_b_conflict.2.2⟩
  exact certified_of (inputs := tryBThenA) (locks := []) (e := b) (by
    intro x hx
    rcases hx with rfl | rfl | rfl <;> decide +kernel)

/-! ## Six validators -/

abbrev Sg6 := Fin 6 × EventId

def vf6 (v : Fin 6) (e : Event) (s : Sg6) : Bool := s == (v, e.id)

def certOf6 (e : Event) (signers : List (Fin 6)) : Cert 6 Sg6 :=
  ⟨e, signers.map fun v => (v, (v, e.id))⟩

def attack6 : Fin 6 → List (Input 6 Sg6)
  | 0 => []
  | 5 => [.voteRequest b, .certificate (certOf6 a [0, 1, 2, 3, 4])]
  | _ => [.voteRequest a, .certificate (certOf6 a [0, 1, 2, 3, 4])]

def run6 (inputs : List (Input 6 Sg6)) : NodeState 6 Sg6 :=
  runNode vf6 5 yes initial inputs

def unforgeable6B : Bool :=
  (List.finRange 6).all fun u =>
    u == 0 || (attack6 u).all fun
      | .voteRequest _ => true
      | .certificate c => c.sigs.all fun p =>
          p.1 == 0 || !(vf6 p.1 c.event p.2) || (run6 (attack6 p.1)).votes.contains c.event

theorem unforgeable6 : Unforgeable vf6 [0] 5 (fun _ => yes) initial attack6 := by
  intro u hu c hc p hp hpf hv
  have huz : (u == (0 : Fin 6)) = false := by simpa using hu
  have hpz : (p.1 == (0 : Fin 6)) = false := by simpa using hpf
  have hcheck : unforgeable6B = true := by decide +kernel
  have h₁ := List.all_eq_true.mp hcheck u (List.mem_finRange u)
  simp only [huz, Bool.false_or] at h₁
  have h₂ := List.all_eq_true.mp h₁ (Input.certificate c) hc
  have h₃ := List.all_eq_true.mp h₂ p hp
  simp only [hpz, hv, Bool.false_or, Bool.not_true] at h₃
  simpa [run6] using h₃

/-- Every hypothesis of `no_double_spend_q` holds with `n = 6`, `q = 5`, in a run where the
sender equivocates and one honest validator voted for the other version. -/
theorem equivocation_run_6_satisfies_hypotheses :
    (6 : Nat) + ([0] : List (Fin 6)).length < 2 * 5 ∧
    Unforgeable vf6 [0] 5 (fun _ => yes) initial attack6 ∧
    b ∈ (run6 (attack6 5)).votes ∧
    a ∈ (run6 (attack6 1)).executed ∧
    a ∈ (run6 (attack6 5)).executed := by
  refine ⟨by decide, unforgeable6, ?_⟩
  decide +kernel

/-! ## Unlocking with six validators -/

def reports6 : Reports 6
  | 0 => some b
  | 5 => some b
  | _ => some a

/-- The hypotheses of `unlock_safe_5f1` can hold, and the faulty validator 0 cannot give `b`
the reports it would need, even with the honest validator 5 that voted for it. -/
theorem unlock_safe_witness :
    2 * 1 + 1 ≤ (reportsFor reports6 [0, 1, 2, 3, 4] a).length ∧
    (reportsFor reports6 (List.finRange 6) b).length ≤ 2 * 1 :=
  by
    have hne : b ≠ a := fun h => a_b_conflict.2.2 h.symm
    have hab := unlock_safe_5f1 (n := 6) (f := 1) rfl [0] [0, 1, 2, 3, 4] [0, 1, 2, 3, 4]
      (by decide) (by decide) (by decide) (by decide) (by decide) reports6 a
      (by
        intro x hx hxf
        right
        simp only [List.mem_cons, List.not_mem_nil, or_false] at hx hxf
        rcases hx with rfl | rfl | rfl | rfl | rfl
        · exact absurd rfl hxf
        · rfl
        · rfl
        · rfl
        · rfl)
      (by
        intro x hx
        simp only [List.mem_cons, List.not_mem_nil, or_false] at hx
        rcases hx with rfl | rfl | rfl | rfl | rfl <;> simp [reports6])
    exact ⟨hab.1, hab.2 b hne⟩

end PSystem.QuorumExamples
