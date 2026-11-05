import PSystem.QuorumSafety

namespace PSystem.Quorum

/-!
# A retry of a closure

Each member votes for one closure per epoch, for good. So a proposer that died can leave votes
on a closure that a retry must not replace: enough of them and no other closure can reach a quorum.
Members answer a retry with the closure they voted for, and the proposer adopts it.

- `blocking_closure_is_seen`: a closure with more than `n - q` voters blocks every other, and any
  `q` reporters include one of its voters. So a retry always hears of the closure that matters.
- `retry_gets_every_vote`: if at most one closure has votes so far, every honest member among the
  reporters can vote for what the proposer picks. With `q` of them, a certificate forms.
- `split_closures_block`: this is not a theorem about all runs. Two closures with votes can block
  each other for good. With `n = 4`, `q = 3`, two votes for each leave no closure with three. Avoiding
  that for sure would take consensus: `docs/PROTOCOL.md` states it as an operating rule.

This is liveness with delivery as a hypothesis, as in `QuorumLiveness.lean`. Safety does not depend on
any of it, since no member ever votes for a second closure.
-/

variable {α : Type} [DecidableEq α]

/-- Member `x` can still vote for `c`: it voted for nothing, or for `c`. -/
def canVote {n : Nat} (voted : Fin n → Option α) (c : α) (x : Fin n) : Bool :=
  match voted x with
  | none => true
  | some d => decide (d = c)

/-- What a proposer hears from its reporters. -/
def adopted {n : Nat} (voted : Fin n → Option α) (reporters : List (Fin n)) : Option α :=
  reporters.findSome? voted

/-- Two lists of distinct members that together exceed `n` have a common member. -/
theorem lists_meet {n : Nat} {A B : List (Fin n)} (hA : A.Nodup) (hB : B.Nodup)
    (h : n < A.length + B.length) : ∃ x, x ∈ A ∧ x ∈ B := by
  refine Classical.byContradiction fun hno => ?_
  have hnd : (A ++ B).Nodup := by
    refine List.nodup_append.mpr ⟨hA, hB, ?_⟩
    intro a ha b hb hab
    subst hab
    exact hno ⟨a, ha, hb⟩
  have hfit : (A ++ B).length ≤ (List.finRange n).length :=
    nodup_length_le_of_subset hnd fun x _ => List.mem_finRange x
  simp only [List.length_append, List.length_finRange] at hfit
  omega

omit [DecidableEq α] in
theorem adopted_some_of_mem {n : Nat} {voted : Fin n → Option α} {reporters : List (Fin n)}
    {x : Fin n} {c : α} (hx : x ∈ reporters) (hv : voted x = some c) :
    (adopted voted reporters).isSome = true := by
  induction reporters with
  | nil => simp at hx
  | cons a t ih =>
      simp only [adopted, List.findSome?_cons]
      cases ha : voted a with
      | some d => simp
      | none =>
          rcases List.mem_cons.mp hx with rfl | hxt
          · rw [hv] at ha; simp at ha
          · exact ih hxt

omit [DecidableEq α] in
/-- Any `q` reporters include a voter of a closure with more than `n - q` voters. -/
theorem blocking_closure_is_seen {n q : Nat} {voted : Fin n → Option α} {c : α}
    {voters reporters : List (Fin n)} (hV : voters.Nodup) (hR : reporters.Nodup)
    (hvoted : ∀ x, x ∈ voters → voted x = some c)
    (hblocks : n - q < voters.length) (hq : q ≤ reporters.length) (hqn : q ≤ n) :
    (adopted voted reporters).isSome = true := by
  obtain ⟨x, hxV, hxR⟩ := lists_meet hV hR (by omega)
  exact adopted_some_of_mem hxR (hvoted x hxV)

omit [DecidableEq α] in
theorem adopted_is_voted {n : Nat} {voted : Fin n → Option α} {reporters : List (Fin n)} {c : α}
    (h : adopted voted reporters = some c) : ∃ x, voted x = some c := by
  induction reporters with
  | nil => simp [adopted] at h
  | cons a t ih =>
      simp only [adopted, List.findSome?_cons] at h
      cases ha : voted a with
      | some d =>
          rw [ha] at h
          simp only [Option.some.injEq] at h
          exact ⟨a, by rw [ha, h]⟩
      | none =>
          rw [ha] at h
          exact ih h

/-- What the proposer picks: what it heard of, or a closure of its own. -/
def picked {n : Nat} (voted : Fin n → Option α) (reporters : List (Fin n)) (own : α) : α :=
  (adopted voted reporters).getD own

/-- With at most one closure voted so far, every member can vote for what the proposer picks, so
`q` reporters give `q` votes. -/
theorem retry_gets_every_vote {n q : Nat} {voted : Fin n → Option α}
    {reporters : List (Fin n)} (own : α)
    (hone : ∀ x y c d, voted x = some c → voted y = some d → c = d)
    (hR : reporters.Nodup) (hq : q ≤ reporters.length) :
    ∃ signers : List (Fin n), signers.Nodup ∧ q ≤ signers.length ∧
      ∀ x, x ∈ signers → canVote voted (picked voted reporters own) x = true := by
  refine ⟨reporters, hR, hq, fun x hxR => ?_⟩
  cases hx : voted x with
  | none => simp [canVote, hx]
  | some d =>
      have hsome := adopted_some_of_mem hxR hx
      cases ha : adopted voted reporters with
      | none => rw [ha] at hsome; simp at hsome
      | some c =>
          obtain ⟨y, hy⟩ := adopted_is_voted ha
          have hdc : d = c := hone x y d c hx hy
          simp [canVote, hx, picked, ha, hdc]

/-- Two votes for each of two closures, with `n = 4`. -/
def splitVotes (x : Fin 4) : Option Nat :=
  if x.val < 2 then some 0 else some 1

/-- No closure can reach a quorum of three from there, whatever it is. -/
theorem split_closures_block (c : Nat) :
    ((List.finRange 4).filter (canVote splitVotes c)).length < 3 := by
  by_cases h0 : c = 0
  · subst h0; decide
  by_cases h1 : c = 1
  · subst h1; decide
  have hc0 : (0 : Nat) ≠ c := fun h => h0 h.symm
  have hc1 : (1 : Nat) ≠ c := fun h => h1 h.symm
  have hnil : (List.finRange 4).filter (canVote splitVotes c) = [] := by
    refine List.filter_eq_nil_iff.mpr fun x _ => ?_
    by_cases hx : x.val < 2 <;> simp [canVote, splitVotes, hx, hc0, hc1]
  rw [hnil]
  decide

/-- It is reachable by a proposer that died and a second one that did not hear of the first: the
hypothesis of `retry_gets_every_vote` is what fails. -/
theorem split_votes_are_two_closures :
    splitVotes ⟨0, by decide⟩ = some 0 ∧ splitVotes ⟨2, by decide⟩ = some 1 :=
  ⟨rfl, rfl⟩

end PSystem.Quorum
