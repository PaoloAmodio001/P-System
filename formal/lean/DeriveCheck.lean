import PSystem.Derive

/-!
Command-line driver for the differential test against the Python
`StateDeriver` (tests/test_lean_differential.py). Not part of the proofs.

Input file: cases separated by a line `---`. Each case has lines

    A <name> <initial balance>
    E <id> <sender> <receiver> <amount> <nonce> <parent,parent,...|->

Output: one line per case, `REJECT` or
`OK <name>=<balance>/<nonce> ...` in the order of the `A` lines.
-/

open PSystem

def parseEvent (w : List String) : Option Event :=
  match w with
  | ["E", id, sender, receiver, amount, nonce, parents] =>
      some {
        id := id.toNat!
        sender
        receiver
        amount := amount.toNat!
        nonce := nonce.toNat!
        parents := if parents = "-" then [] else (parents.splitOn ",").map String.toNat!
      }
  | _ => none

def parseAccount (w : List String) : Option (String × Nat) :=
  match w with
  | ["A", name, balance] => some (name, balance.toNat!)
  | _ => none

def runCase (lines : List String) : String :=
  let words := lines.map (·.splitOn " ")
  let accounts := words.filterMap parseAccount
  let events := words.filterMap parseEvent
  let initial : State :=
    { balance := fun id => (accounts.lookup id).getD 0
      nonce := fun _ => 0 }
  match derive initial events with
  | none => "REJECT"
  | some t =>
      "OK " ++ " ".intercalate
        (accounts.map fun (name, _) => s!"{name}={t.balance name}/{t.nonce name}")

def splitCases : List String → List (List String)
  | [] => [[]]
  | line :: rest =>
      match splitCases rest with
      | [] => [[line]]
      | current :: others =>
          if line = "---" then [] :: current :: others
          else (line :: current) :: others

def main (args : List String) : IO UInt32 := do
  match args with
  | [path] =>
      let input ← IO.FS.readFile path
      let lines := (input.splitOn "\n").filter (· ≠ "")
      for case in splitCases lines do
        IO.println (runCase case)
      return 0
  | _ =>
      IO.eprintln "usage: derive_check <cases-file>"
      return 2
