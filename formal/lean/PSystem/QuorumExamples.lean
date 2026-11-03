import PSystem.DeriveExamples
import PSystem.Quorum

/-!
Executable sanity checks for the quorum model (not theorems, not counted as
properties). Committee of `n = 4`, `f = 1`, quorum 3. They test that the
definitions behave as intended; the safety theorems are still open.
-/

namespace PSystem.QuorumExamples

open PSystem PSystem.Quorum
open PSystem.DeriveExamples (initial accounts ev)

/-- Symbolic signature: the signer and the id of the signed event. -/
abbrev Sg := Fin 4 × EventId

def vf (v : Fin 4) (e : Event) (s : Sg) : Bool := s == (v, e.id)

def certOf (e : Event) (signers : List (Fin 4)) : Cert 4 Sg :=
  ⟨e, signers.map fun v => (v, (v, e.id))⟩

def yes (_ : Event) : Bool := true

def run (q : Nat) (inputs : List (Input 4 Sg)) : NodeState 4 Sg :=
  runNode vf q yes initial inputs

def votedIds (st : NodeState 4 Sg) : List EventId := st.votes.map Event.id
def execIds (st : NodeState 4 Sg) : List EventId := st.executed.map Event.id

-- Two conflicting events: alice signs both versions of nonce 0.
def a := ev 1 "alice" "bob" 8 0
def b := ev 2 "alice" "carol" 8 0

/-! ## The vote lock -/

-- A validator signs only the first alternative it receives, in either order.
#guard votedIds (run 3 [.voteRequest a, .voteRequest b]) == [1]
#guard votedIds (run 3 [.voteRequest b, .voteRequest a]) == [2]

-- Signing the same event again is allowed.
#guard votedIds (run 3 [.voteRequest a, .voteRequest a]) == [1, 1]

-- The lock is per (sender, nonce): other nonces and senders are free.
#guard votedIds (run 3 [.voteRequest a, .voteRequest (ev 3 "alice" "bob" 1 1)]) == [3, 1]
#guard votedIds (run 3 [.voteRequest a, .voteRequest (ev 3 "bob" "carol" 1 0)]) == [3, 1]

-- The lock also covers a different event with the same id.
#guard votedIds (run 3 [.voteRequest a, .voteRequest (ev 1 "bob" "carol" 1 0)]) == [1]

-- A request the node's own check refuses takes no vote and no lock.
#guard votedIds (runNode vf 3 (fun e => e.id != 2) initial
  [.voteRequest b, .voteRequest a]) == [1]

/-! ## Certificate validity -/

#guard execIds (run 3 [.certificate (certOf a [1, 2, 3])]) == [1]
-- Too few signers.
#guard execIds (run 3 [.certificate (certOf a [1, 2])]) == []
-- A repeated signer does not count twice.
#guard execIds (run 3 [.certificate (certOf a [1, 1, 2])]) == []
#guard execIds (run 3 [.certificate (certOf a [1, 2, 2, 2])]) == []
-- A signature on another event is not valid for this one.
#guard execIds (run 3 [.certificate ⟨a, [(1, (1, 1)), (2, (2, 1)), (3, (3, 2))]⟩]) == []
-- A signature attributed to the wrong signer is not valid.
#guard execIds (run 3 [.certificate ⟨a, [(1, (1, 1)), (2, (2, 1)), (3, (0, 1))]⟩]) == []

/-! ## Execution conditions -/

def a1 := ev 3 "alice" "bob" 1 1 [1]

-- A certificate ahead of its nonce and parent has no effect; delivering it
-- again after its predecessor succeeds.
#guard execIds (run 3 [.certificate (certOf a1 [1, 2, 3])]) == []
#guard execIds (run 3 [.certificate (certOf a1 [1, 2, 3]),
                       .certificate (certOf a [1, 2, 3]),
                       .certificate (certOf a1 [1, 2, 3])]) == [1, 3]

-- Right nonce and enough funds, but a parent the node has not executed.
#guard execIds (run 3 [.certificate (certOf (ev 5 "alice" "bob" 1 0 [99]) [1, 2, 3])]) == []

-- A delivered duplicate is not executed twice.
#guard execIds (run 3 [.certificate (certOf a [1, 2, 3]),
                       .certificate (certOf a [1, 2, 3])]) == [1]
#guard accounts (run 3 [.certificate (certOf a [1, 2, 3]),
                        .certificate (certOf a [1, 2, 3])]).state == [2, 8, 0, 0]

-- Insufficient balance: a certificate does not create funds.
#guard execIds (run 3 [.certificate (certOf (ev 4 "bob" "carol" 1 0) [1, 2, 3])]) == []
#guard execIds (run 3 [.certificate (certOf (ev 4 "alice" "bob" 11 0) [1, 2, 3])]) == []

-- A different event with an id already executed is refused.
#guard execIds (run 3 [.certificate (certOf a [1, 2, 3]),
                       .certificate (certOf (ev 1 "alice" "bob" 1 1) [1, 2, 3])]) == [1]

-- One node never executes both alternatives, even with certificates for both
-- and no quorum at all: this is the nonce check. The result to prove is
-- between two nodes.
#guard execIds (run 0 [.certificate (certOf a []), .certificate (certOf b [])]) == [1]

/-! ## Runs: inputs for each node -/

/-- Boolean check of `Unforgeable` for these runs, with `auth` always true. -/
def unforgeableB (faulty : List (Fin 4)) (q : Nat)
    (inputs : Fin 4 → List (Input 4 Sg)) : Bool :=
  (List.finRange 4).all fun u =>
    faulty.contains u || (inputs u).all fun
      | .voteRequest _ => true
      | .certificate c => c.sigs.all fun p =>
          faulty.contains p.1 || !(vf p.1 c.event p.2) ||
            (run q (inputs p.1)).votes.contains c.event

/-- Execution of every node in a run. -/
def allExec (q : Nat) (inputs : Fin 4 → List (Input 4 Sg)) : List (List EventId) :=
  (List.finRange 4).map fun v => execIds (run q (inputs v))

/-! ### Quorum 3, one faulty validator: alice equivocates, node 0 signs anything -/

def certA := certOf a [0, 1, 3]

def attack : Fin 4 → List (Input 4 Sg)
  | 1 => [.voteRequest a, .certificate certA]
  | 2 => [.voteRequest b, .certificate certA]
  | 3 => [.voteRequest a, .voteRequest b, .certificate certA]
  | _ => []

-- The hypothesis holds, and the three honest nodes execute the same event,
-- including node 2, which had voted for the alternative.
#guard unforgeableB [0] 3 attack
#guard allExec 3 attack == [[], [1], [1], [1]]

-- The only real signatures on `b` are those of nodes 0 and 2: too few.
def attackB : Fin 4 → List (Input 4 Sg)
  | 1 => [.voteRequest a, .certificate (certOf b [0, 2])]
  | 2 => [.voteRequest b, .certificate (certOf b [0, 2])]
  | 3 => [.voteRequest a, .voteRequest b, .certificate (certOf b [0, 2])]
  | _ => []

#guard unforgeableB [0] 3 attackB
#guard allExec 3 attackB == [[], [], [], []]

/-! ### The conditions matter: without each one a fork appears -/

-- Signature of node 3 on `b`, which it never gave: the hypothesis fails, and
-- nodes 1 and 2 execute conflicting events.
def forged : Fin 4 → List (Input 4 Sg)
  | 1 => [.voteRequest a, .certificate certA]
  | 2 => [.voteRequest b, .certificate (certOf b [0, 2, 3])]
  | 3 => [.voteRequest a]
  | _ => []

#guard !unforgeableB [0] 3 forged
#guard allExec 3 forged == [[], [1], [2], []]

-- Quorum 2 with one faulty validator: no forgery is needed for a fork.
def smallQuorum : Fin 4 → List (Input 4 Sg)
  | 1 => [.voteRequest a, .certificate (certOf a [0, 1])]
  | 2 => [.voteRequest b, .certificate (certOf b [0, 2])]
  | _ => []

#guard unforgeableB [0] 2 smallQuorum
#guard allExec 2 smallQuorum == [[], [1], [2], []]
#guard accounts (run 2 (smallQuorum 1)).state == [2, 8, 0, 0]
#guard accounts (run 2 (smallQuorum 2)).state == [2, 0, 8, 0]

-- Quorum 3 with two faulty validators: f + 1 faults also give a fork.
def tooManyFaults : Fin 4 → List (Input 4 Sg)
  | 2 => [.voteRequest a, .certificate (certOf a [0, 1, 2])]
  | 3 => [.voteRequest b, .certificate (certOf b [0, 1, 3])]
  | _ => []

#guard unforgeableB [0, 1] 3 tooManyFaults
#guard allExec 3 tooManyFaults == [[], [], [1], [2]]

/-! ## Link to `derive` and exchange of logs -/

def x := ev 1 "alice" "bob" 6 0
def y := ev 2 "bob" "carol" 4 0          -- spends funds received from `x`
def z := ev 3 "alice" "dave" 2 1

def certsFor (events : List Event) : List (Input 4 Sg) :=
  events.map fun e => .certificate (certOf e [1, 2, 3])

def nodeU := certsFor [x, y]
def nodeV := certsFor [x, z]

-- The state of a node is what `derive` computes from what it executed.
#guard (derive initial (run 3 nodeU).executed).map accounts ==
  some (accounts (run 3 nodeU).state)
#guard (derive initial (run 3 nodeV).executed).map accounts ==
  some (accounts (run 3 nodeV).state)

-- Different knowledge, different state: delay, not yet convergence.
#guard accounts (run 3 nodeU).state == [4, 2, 4, 0]
#guard accounts (run 3 nodeV).state == [2, 6, 0, 2]

/-- A node's log, as inputs for another node. -/
def logInputs (st : NodeState 4 Sg) : List (Input 4 Sg) :=
  st.log.map .certificate

-- After exchanging logs both nodes reach the same state, by different orders.
#guard execIds (run 3 (nodeU ++ logInputs (run 3 nodeV))) == [1, 2, 3]
#guard execIds (run 3 (nodeV ++ logInputs (run 3 nodeU))) == [1, 3, 2]
#guard accounts (run 3 (nodeU ++ logInputs (run 3 nodeV))).state == [2, 2, 4, 2]
#guard accounts (run 3 (nodeV ++ logInputs (run 3 nodeU))).state == [2, 2, 4, 2]

end PSystem.QuorumExamples
