import Std
import Std.Tactic

namespace PSystem

/-!
# Basic definitions

Events, account state and the single-event transition used by the
convergence results. The former independence, permutation, conflict and
acyclicity material was removed (see the tag `pre-lean-cleanup` and
`docs/PROOF-OBLIGATIONS.md`): it was superseded by `Convergence.lean`, or
degenerate (`Acyclic` held only for events without parents).
-/

abbrev EventId := Nat
abbrev Identity := String
abbrev Nonce := Nat
abbrev Amount := Nat

structure Event where
  id : EventId
  sender : Identity
  receiver : Identity
  amount : Amount
  nonce : Nonce
  parents : List EventId
  deriving DecidableEq, Repr

structure State where
  balance : Identity → Nat
  nonce : Identity → Nonce

/--
A transfer event is executable when the amount is positive, sender and
receiver differ, the sender has sufficient balance and the nonce matches
the current sender nonce.
-/
def Executable (s : State) (e : Event) : Prop :=
  e.amount > 0 ∧
  e.sender ≠ e.receiver ∧
  s.balance e.sender ≥ e.amount ∧
  s.nonce e.sender = e.nonce

/--
Apply one transfer: debit the sender, credit the receiver, advance the
sender nonce. It does not check `Executable` (subtraction truncates at
zero); the convergence results always pair it with `ExecutableRun`.
-/
def ApplyEvent (s : State) (e : Event) : State :=
  {
    balance := fun id =>
      if id = e.sender then
        s.balance id - e.amount
      else if id = e.receiver then
        s.balance id + e.amount
      else
        s.balance id

    nonce := fun id =>
      if id = e.sender then
        s.nonce id + 1
      else
        s.nonce id
  }

/-- Apply a list of events from left to right. -/
def ApplyEvents : State → List Event → State
  | s, [] => s
  | s, e :: rest => ApplyEvents (ApplyEvent s e) rest

theorem apply_events_append
    (s : State)
    (xs ys : List Event) :
    ApplyEvents s (xs ++ ys) =
      ApplyEvents (ApplyEvents s xs) ys := by
  induction xs generalizing s with
  | nil =>
      rfl
  | cons x xs ih =>
      simp [ApplyEvents, ih]

/-- Two states are equal when balances and nonces are equal. -/
theorem state_eq_of_fields_eq
    (s t : State)
    (hbalance : s.balance = t.balance)
    (hnonce : s.nonce = t.nonce) :
    s = t := by
  cases s
  cases t
  cases hbalance
  cases hnonce
  rfl

end PSystem
