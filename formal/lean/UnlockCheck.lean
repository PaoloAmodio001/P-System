import PSystem.QuorumUnlock

/-!
Command-line driver for the differential test against the Python closure with unlocking
(tests/test_unlock_differential.py). Not part of the proofs. It runs `thresholdLocks` from
`PSystem.QuorumUnlock`, with no logic of its own apart from parsing and printing.

Input file: cases separated by a line `---`. Each case:

    N <members>
    T <threshold>
    R <reporter>                                    a member among the reporters of the closure
    E <reporter> <id> <sender> <receiver> <amount> <nonce>      an event in what it reported

Output, for each case, one line with the ids of the locks, sorted, or `-`. Malformed input is an error with
exit code 1, never a default.
-/

open PSystem PSystem.Quorum

structure RawUnlockCase where
  n : Nat := 0
  threshold : Nat := 0
  reporters : List Nat := []
  events : List (Nat × Event) := []

def parseNatU (s : String) : Except String Nat :=
  match s.toNat? with
  | some k => .ok k
  | none => .error s!"not a natural number: '{s}'"

def parseUnlockLine (c : RawUnlockCase) (line : String) : Except String RawUnlockCase :=
  match line.splitOn " " with
  | ["N", n] => do return { c with n := ← parseNatU n }
  | ["T", t] => do return { c with threshold := ← parseNatU t }
  | ["R", r] => do return { c with reporters := c.reporters ++ [← parseNatU r] }
  | ["E", r, id, s, re, a, k] => do
      let event : Event := {
        id := ← parseNatU id
        sender := s
        receiver := re
        amount := ← parseNatU a
        nonce := ← parseNatU k
        parents := []
      }
      return { c with events := c.events ++ [(← parseNatU r, event)] }
  | _ => .error s!"bad line: '{line}'"

def runUnlockCase (lines : List String) : Except String String := do
  let c ← lines.foldlM parseUnlockLine {}
  let reporters : List (Fin c.n) ← c.reporters.mapM fun r =>
    if h : r < c.n then .ok ⟨r, h⟩ else .error s!"no such member: {r}"
  let reports : Fin c.n → List Event := fun x =>
    (c.events.filter (·.1 == x.val)).map (·.2)
  let locks := thresholdLocks c.threshold reporters reports
  let ids := (locks.map Event.id).eraseDups.mergeSort
  return if ids.isEmpty then "-" else ",".intercalate (ids.map toString)

def splitUnlockCases (lines : List String) : List (List String) :=
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
      for case in splitUnlockCases lines do
        match runUnlockCase case with
        | .error message =>
            IO.eprintln s!"unlock_check: {message}"
            return 1
        | .ok output => IO.println output
      return 0
  | _ =>
      IO.eprintln "usage: unlock_check <cases-file>"
      return 2
