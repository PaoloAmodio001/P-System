import PSystem.QuorumEpochs

/-!
Command-line driver for the differential test against the Python vote store across epochs
(tests/test_epoch_differential.py). Not part of the proofs. It runs `runEpoch`, `reportOf` and
`lockAllows` from `PSystem.QuorumEpochs`, with no logic of its own apart from parsing and printing.

Input file: cases separated by a line `---`. Each case is one epoch of one validator:

    L <id> <sender> <receiver> <amount> <nonce> <parents>   a lock from earlier epochs
    U <id>                                                  the check `auth` refuses this id
    V <id> <sender> <receiver> <amount> <nonce> <parents>   a vote request
    X                                                       close

`<parents>` is `p,p,...` or `-`. Lock and refused lines come before the inputs.

Output, for each case: one line for the state before any input and one after each input,
computed by `runEpoch` on that prefix of the inputs, then `---`:

    votes=<ids|->;closed=<0|1>;report=<ids|->

`votes` and `report` are sorted. Malformed input is an error with exit code 1, never a default.
-/

open PSystem PSystem.Quorum

structure RawEpochCase where
  locks : List Event := []
  refused : List EventId := []
  inputs : List EpochInput := []

def parseNat (s : String) : Except String Nat :=
  match s.toNat? with
  | some k => .ok k
  | none => .error s!"not a natural number: '{s}'"

def parseParents (s : String) : Except String (List EventId) :=
  if s = "-" then .ok [] else (s.splitOn ",").mapM parseNat

def parseEvent (id sender receiver amount nonce parents : String) : Except String Event := do
  return {
    id := ← parseNat id
    sender
    receiver
    amount := ← parseNat amount
    nonce := ← parseNat nonce
    parents := ← parseParents parents
  }

def parseLine (c : RawEpochCase) (line : String) : Except String RawEpochCase :=
  match line.splitOn " " with
  | ["L", id, s, r, a, k, p] => do
      if !c.inputs.isEmpty then .error "a lock after the inputs" else
      return { c with locks := c.locks ++ [← parseEvent id s r a k p] }
  | ["U", id] => do
      if !c.inputs.isEmpty then .error "a refused id after the inputs" else
      return { c with refused := c.refused ++ [← parseNat id] }
  | ["V", id, s, r, a, k, p] => do
      return { c with inputs := c.inputs ++ [.voteRequest (← parseEvent id s r a k p)] }
  | ["X"] => return { c with inputs := c.inputs ++ [.close] }
  | _ => .error s!"bad line: '{line}'"

def idList (events : List Event) : String :=
  let ids := (events.map Event.id).eraseDups.mergeSort
  if ids.isEmpty then "-" else ",".intercalate (ids.map toString)

def runCase (lines : List String) : Except String (List String) := do
  let c ← lines.foldlM parseLine {}
  let auth : Event → Bool := fun e => !c.refused.contains e.id
  return (List.range (c.inputs.length + 1)).map fun k =>
    let seen := c.inputs.take k
    let st := runEpoch c.locks auth seen
    let closed := if st.closed then "1" else "0"
    s!"votes={idList st.votes};closed={closed};report={idList (reportOf c.locks auth seen)}"

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
            IO.eprintln s!"epoch_check: {message}"
            return 1
        | .ok output =>
            for line in output do
              IO.println line
            IO.println "---"
      return 0
  | _ =>
      IO.eprintln "usage: epoch_check <cases-file>"
      return 2
