import PSystem.QuorumExamples
import PSystem.QuorumConvergence

namespace PSystem.QuorumExamples

/-!
# The Byzantine results are not vacuous and their hypotheses matter (obligation O7)

Concrete witnesses for `n = 4`, `f = 1`, on the runs of `QuorumExamples`.

- `equivocation_run_satisfies_hypotheses`: all the hypotheses of
  `no_double_spend` hold in a run where a sender really signs two conflicting
  versions, both get honest votes, and honest nodes execute one of them.
- The others each change one condition and get a fork between nodes:
  `fork_with_small_quorum` (quorum `2f`), `fork_with_too_many_faults` (`f+1`
  faulty validators), `fork_with_forged_signature` (no `Unforgeable`) and
  `fork_with_faulty_receiver` (a node outside the honest ones).

These are computations on one instance, not general properties, and they do
not show tightness for other values of `f`. Their job is to show that the
main theorem says something and that its hypotheses are used.

For `convergence_after_exchange`: `exchange_run_diverges_then_converges` is a run
where two honest nodes are in different states before the exchange and in the same
state after it, and `no_convergence_with_small_quorum` shows that it fails with
quorum `2f`.

`unforgeableB_sound` connects the Boolean check used by the `#guard` lines to
the `Unforgeable` hypothesis of the theorem.
-/

open PSystem PSystem.Quorum
open PSystem.DeriveExamples (initial)

/-- The Boolean check of the examples implies the hypothesis of the theorem. -/
theorem unforgeableB_sound {faulty : List (Fin 4)} {q : Nat}
    {inputs : Fin 4 → List (Input 4 Sg)}
    (h : unforgeableB faulty q inputs = true) :
    Unforgeable vf faulty q (fun _ => yes) initial inputs := by
  intro u hu c hc p hp hpf hv
  have hu' : faulty.contains u = false := by simpa using hu
  have hpf' : faulty.contains p.1 = false := by simpa using hpf
  have h₁ := List.all_eq_true.mp h u (List.mem_finRange u)
  simp only [hu', Bool.false_or] at h₁
  have h₂ := List.all_eq_true.mp h₁ (Input.certificate c) hc
  have h₃ := List.all_eq_true.mp h₂ p hp
  simp only [hpf', hv, Bool.false_or, Bool.not_true] at h₃
  simpa [run] using h₃

/-- `a` and `b` are two versions of one spend: same sender and nonce, different events. -/
theorem a_b_conflict : a.sender = b.sender ∧ a.nonce = b.nonce ∧ a ≠ b := by
  decide +kernel

/--
Non-vacuity: every hypothesis of `no_double_spend` holds in a run where the
sender equivocates. Both versions receive honest votes, node 0 is faulty and
signs what it wants, and the three honest nodes execute the same version,
including node 2, which voted for the other one.
-/
theorem equivocation_run_satisfies_hypotheses :
    (4 : Nat) = 3 * 1 + 1 ∧
    ([0] : List (Fin 4)).length ≤ 1 ∧
    Unforgeable vf [0] 3 (fun _ => yes) initial attack ∧
    a ∈ (run 3 (attack 1)).votes ∧ b ∈ (run 3 (attack 2)).votes ∧
    a ∈ (run 3 (attack 1)).executed ∧
    a ∈ (run 3 (attack 2)).executed ∧
    a ∈ (run 3 (attack 3)).executed := by
  refine ⟨rfl, by decide, unforgeableB_sound (by decide +kernel), ?_⟩
  decide +kernel

/-- Quorum `2f` instead of `2f+1`: honest nodes fork, with no forged signature. -/
theorem fork_with_small_quorum :
    ([0] : List (Fin 4)).length ≤ 1 ∧
    Unforgeable vf [0] 2 (fun _ => yes) initial smallQuorum ∧
    (1 : Fin 4) ∉ ([0] : List (Fin 4)) ∧ (2 : Fin 4) ∉ ([0] : List (Fin 4)) ∧
    a ∈ (run 2 (smallQuorum 1)).executed ∧ b ∈ (run 2 (smallQuorum 2)).executed := by
  refine ⟨by decide, unforgeableB_sound (by decide +kernel), by decide, by decide, ?_⟩
  decide +kernel

/-- `f+1` faulty validators with quorum `2f+1`: honest nodes fork, with no forged signature. -/
theorem fork_with_too_many_faults :
    ([0, 1] : List (Fin 4)).length = 2 ∧
    Unforgeable vf [0, 1] 3 (fun _ => yes) initial tooManyFaults ∧
    (2 : Fin 4) ∉ ([0, 1] : List (Fin 4)) ∧ (3 : Fin 4) ∉ ([0, 1] : List (Fin 4)) ∧
    a ∈ (run 3 (tooManyFaults 2)).executed ∧ b ∈ (run 3 (tooManyFaults 3)).executed := by
  refine ⟨rfl, unforgeableB_sound (by decide +kernel), by decide, by decide, ?_⟩
  decide +kernel

/-- With correct `n`, `f` and quorum, a forged signature gives a fork between honest nodes. -/
theorem fork_with_forged_signature :
    ([0] : List (Fin 4)).length ≤ 1 ∧
    (1 : Fin 4) ∉ ([0] : List (Fin 4)) ∧ (2 : Fin 4) ∉ ([0] : List (Fin 4)) ∧
    a ∈ (run 3 (forged 1)).executed ∧ b ∈ (run 3 (forged 2)).executed := by
  refine ⟨by decide, by decide, by decide, ?_⟩
  decide +kernel

/--
That run violates `Unforgeable`, derived from `no_double_spend` and not from the
Boolean check: the main theorem rules out exactly this fork.
-/
theorem forged_run_not_unforgeable :
    ¬ Unforgeable vf [0] 3 (fun _ => yes) initial forged := by
  intro hsig
  obtain ⟨hf, h1, h2, ha, hb⟩ := fork_with_forged_signature
  have heq : a = b :=
    no_double_spend (n := 4) (f := 1) rfl [0] hf vf (fun _ => yes) initial forged hsig
      h1 h2 ha hb a_b_conflict.1 a_b_conflict.2.1
  exact a_b_conflict.2.2 heq

/-- A certificate with a false signature shown only to the faulty node 0. -/
def faultyReceiver : Fin 4 → List (Input 4 Sg)
  | 0 => [.certificate (certOf b [0, 2, 3])]
  | 1 => [.voteRequest a, .certificate certA]
  | 2 => [.voteRequest b]
  | 3 => [.voteRequest a]

/--
The hypotheses other than `hu` and `hv` hold, yet what `runNode` computes for the
faulty node conflicts with an honest node. So the theorem cannot be extended to
faulty receivers, and `Unforgeable` says nothing about what they are shown.
-/
theorem fork_with_faulty_receiver :
    ([0] : List (Fin 4)).length ≤ 1 ∧
    Unforgeable vf [0] 3 (fun _ => yes) initial faultyReceiver ∧
    (0 : Fin 4) ∈ ([0] : List (Fin 4)) ∧ (1 : Fin 4) ∉ ([0] : List (Fin 4)) ∧
    b ∈ (run 3 (faultyReceiver 0)).executed ∧ a ∈ (run 3 (faultyReceiver 1)).executed := by
  refine ⟨by decide, unforgeableB_sound (by decide +kernel), by decide, by decide, ?_⟩
  decide +kernel

/-- Everyone votes for the three compatible events; node 1 gets certificates for
`x, y` and node 2 for `x, z`. -/
def exchangeRun : Fin 4 → List (Input 4 Sg)
  | 1 => [x, y, z].map .voteRequest ++ certsFor [x, y]
  | 2 => [x, y, z].map .voteRequest ++ certsFor [x, z]
  | 3 => [x, y, z].map .voteRequest
  | _ => []

/--
The hypotheses of `convergence_after_exchange` hold in a run where two honest
nodes really differ before the exchange. After it they are in the same state,
by the theorem, and each has executed an event it did not have.
-/
theorem exchange_run_diverges_then_converges :
    Unforgeable vf [0] 3 (fun _ => yes) initial exchangeRun ∧
    (run 3 (exchangeRun 1)).state.balance "bob" ≠
      (run 3 (exchangeRun 2)).state.balance "bob" ∧
    z ∉ (run 3 (exchangeRun 1)).executed ∧
    z ∈ (run 3 (exchangeRun 1 ++ (run 3 (exchangeRun 2)).log.map .certificate)).executed ∧
    (run 3 (exchangeRun 1 ++ (run 3 (exchangeRun 2 ++ [])).log.map .certificate)).state =
      (run 3 (exchangeRun 2 ++ (run 3 (exchangeRun 1 ++ [])).log.map .certificate)).state := by
  have hsig : Unforgeable vf [0] 3 (fun _ => yes) initial exchangeRun :=
    unforgeableB_sound (by decide +kernel)
  refine ⟨hsig, by decide +kernel, by decide +kernel, by decide +kernel, ?_⟩
  exact convergence_after_exchange (n := 4) (f := 1) (u := 1) (v := 2) rfl [0]
    (by decide) vf (fun _ => yes) initial exchangeRun hsig (by decide) (by decide)

/-- With quorum `2f` two honest nodes stay in different states after the exchange:
each holds a conflicting event, so the one it receives can never run. -/
theorem no_convergence_with_small_quorum :
    Unforgeable vf [0] 2 (fun _ => yes) initial smallQuorum ∧
    (run 2 (smallQuorum 1 ++ (run 2 (smallQuorum 2)).log.map .certificate)).state.balance "bob" ≠
      (run 2 (smallQuorum 2 ++ (run 2 (smallQuorum 1)).log.map .certificate)).state.balance "bob" := by
  exact ⟨unforgeableB_sound (by decide +kernel), by decide +kernel⟩

end PSystem.QuorumExamples
