import PSystem.Quorum

/-!
Command-line driver for the differential test against the Python quorum replica
(tests/test_quorum_differential.py). Not part of the proofs. It runs `runNode`
from `PSystem.Quorum`, with no logic of its own apart from parsing and printing.

Input file: cases separated by a line `---`. Each case has lines, in this order
for the inputs:

    N <committee size>
    Q <quorum>
    A <name> <initial balance> <initial nonce>
    U <id>                                  (the check `auth` refuses this id)
    V <id> <sender> <receiver> <amount> <nonce> <parents>
    C <id> <sender> <receiver> <amount> <nonce> <parents> <signatures>

`<parents>` is `p,p,...` or `-`. `<signatures>` is `v:s:i,...` or `-`: an entry
attributed to validator `v`, whose symbolic signature was made by `s` on id `i`.
It verifies when `s = v` and `i` is the id of the event.

Output, for each case: one line for the state before any input and one after
each input, computed by `runNode` on that prefix of the inputs, then `---`:

    votes=<ids|->;exec=<ids|->;<name>=<balance>/<nonce> ...

`votes` is sorted and without repetitions, because voting again for one event
repeats it in the list; `exec` is in execution order. Malformed input is an error
with exit code 1, never a default value.
-/

open PSystem PSystem.Quorum

abbrev Sg := Nat × EventId

def verifySymbolic {n : Nat} (v : Fin n) (e : Event) (s : Sg) : Bool :=
  s.1 == v.val && s.2 == e.id

inductive RawInput where
  | vote (e : Event)
  | cert (e : Event) (sigs : List (Nat × Sg))

structure RawCase where
  n : Nat := 0
  q : Nat := 0
  accounts : List (String × Nat × Nat) := []
  refused : List EventId := []
  inputs : List RawInput := []

def parseNat (s : String) : Except String Nat :=
  match s.toNat? with
  | some k => .ok k
  | none => .error s!"not a natural number: '{s}'"

def parseParents (s : String) : Except String (List EventId) :=
  if s = "-" then .ok [] else (s.splitOn ",").mapM parseNat

def parseSig (s : String) : Except String (Nat × Sg) :=
  match s.splitOn ":" with
  | [v, signer, id] => do
      return (← parseNat v, ← parseNat signer, ← parseNat id)
  | _ => .error s!"bad signature: '{s}'"

def parseSigs (s : String) : Except String (List (Nat × Sg)) :=
  if s = "-" then .ok [] else (s.splitOn ",").mapM parseSig

def parseEvent (id sender receiver amount nonce parents : String) : Except String Event := do
  return {
    id := ← parseNat id
    sender
    receiver
    amount := ← parseNat amount
    nonce := ← parseNat nonce
    parents := ← parseParents parents
  }

def parseLine (c : RawCase) (line : String) : Except String RawCase :=
  match line.splitOn " " with
  | ["N", n] => do return { c with n := ← parseNat n }
  | ["Q", q] => do return { c with q := ← parseNat q }
  | ["A", name, balance, nonce] => do
      return { c with accounts := c.accounts ++ [(name, ← parseNat balance, ← parseNat nonce)] }
  | ["U", id] => do return { c with refused := c.refused ++ [← parseNat id] }
  | ["V", id, s, r, a, k, p] => do
      return { c with inputs := c.inputs ++ [.vote (← parseEvent id s r a k p)] }
  | ["C", id, s, r, a, k, p, sigs] => do
      return { c with inputs := c.inputs ++ [.cert (← parseEvent id s r a k p) (← parseSigs sigs)] }
  | _ => .error s!"bad line: '{line}'"

def toInput (n : Nat) : RawInput → Except String (Input n Sg)
  | .vote e => .ok (.voteRequest e)
  | .cert e sigs => do
      let checked ← sigs.mapM fun (v, s) =>
        if h : v < n then .ok ((⟨v, h⟩ : Fin n), s)
        else .error s!"signer {v} is outside a committee of {n}"
      return .certificate ⟨e, checked⟩

def idList (ids : List EventId) : String :=
  if ids.isEmpty then "-" else ",".intercalate (ids.map toString)

def showState {n : Nat} (accounts : List (String × Nat × Nat)) (st : NodeState n Sg) : String :=
  let votes := (st.votes.map Event.id).eraseDups.mergeSort
  let exec := st.executed.map Event.id
  let shown := accounts.map fun (name, _, _) =>
    s!"{name}={st.state.balance name}/{st.state.nonce name}"
  s!"votes={idList votes};exec={idList exec};" ++ " ".intercalate shown

def runCase (lines : List String) : Except String (List String) := do
  let c ← lines.foldlM parseLine {}
  let inputs ← c.inputs.mapM (toInput c.n)
  let s₀ : State :=
    { balance := fun id => ((c.accounts.lookup id).map (·.1)).getD 0
      nonce := fun id => ((c.accounts.lookup id).map (·.2)).getD 0 }
  let auth : Event → Bool := fun e => !c.refused.contains e.id
  return (List.range (inputs.length + 1)).map fun k =>
    showState c.accounts (runNode verifySymbolic c.q auth s₀ (inputs.take k))

def splitCases (lines : List String) : List (List String) :=
  let (done, current) := lines.foldl
    (fun (acc : List (List String) × List String) line =>
      if line = "---" then (acc.2.reverse :: acc.1, [])
      else (acc.1, line :: acc.2))
    ([], [])
  (current.reverse :: done).reverse

def main (args : List String) : IO UInt32 := do
  match args with
  | [path] =>
      let input ← IO.FS.readFile path
      let lines := (input.splitOn "\n").filter (· ≠ "")
      for case in splitCases lines do
        match runCase case with
        | .error message =>
            IO.eprintln s!"quorum_check: {message}"
            return 1
        | .ok output =>
            for line in output do
              IO.println line
            IO.println "---"
      return 0
  | _ =>
      IO.eprintln "usage: quorum_check <cases-file>"
      return 2
