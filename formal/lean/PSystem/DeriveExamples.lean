import PSystem.Derive

/-!
Executable sanity checks for `derive` (not theorems, not counted as
properties). They mirror cases from `tests/test_transitive_relevance.py`
and the commit 538ee51 regression.
-/

namespace PSystem.DeriveExamples

open PSystem

def initial : State :=
  { balance := fun id => if id = "alice" then 10 else 0
    nonce := fun _ => 0 }

def accounts (s : State) : List Nat :=
  ["alice", "bob", "carol", "dave"].map s.balance

def ev (id : EventId) (sender receiver : Identity) (amount : Amount)
    (nonce : Nonce) (parents : List EventId := []) : Event :=
  { id, sender, receiver, amount, nonce, parents }

-- Chain alice -> bob -> carol -> dave with declared parents.
def chainA := ev 30 "alice" "bob" 5 0
def chainB := ev 20 "bob" "carol" 3 0 [30]
def chainC := ev 10 "carol" "dave" 2 0 [20]

#guard ([[chainA, chainB, chainC], [chainA, chainC, chainB],
         [chainB, chainA, chainC], [chainB, chainC, chainA],
         [chainC, chainA, chainB], [chainC, chainB, chainA]].map
          (fun evs => (derive initial evs).map accounts)).all
          (· == some [5, 2, 1, 2])

-- Implicit funding (no declared parent); the spend has the smaller id.
-- Before 538ee51 the smallest ready id ran first and the batch failed.
def spend := ev 1 "bob" "carol" 3 0
def funding := ev 2 "alice" "bob" 4 0

#guard (derive initial [spend, funding]).map accounts == some [6, 1, 3, 0]
#guard (derive initial [funding, spend]).map accounts == some [6, 1, 3, 0]

-- Conflict: same sender and nonce. Only one can run, so the batch fails.
#guard (derive initial [ev 1 "alice" "bob" 3 0, ev 2 "alice" "carol" 5 0]).isNone

-- Unknown parent: never ready.
#guard (derive initial [ev 1 "alice" "bob" 3 0 [99]]).isNone

-- Insufficient balance.
#guard (derive initial [ev 1 "bob" "carol" 1 0]).isNone

-- Invalid amount and self-transfer are rejected.
#guard (derive initial [ev 1 "alice" "bob" 0 0]).isNone
#guard (derive initial [ev 1 "alice" "alice" 1 0]).isNone

-- Empty history.
#guard (derive initial []).map accounts == some [10, 0, 0, 0]

end PSystem.DeriveExamples
