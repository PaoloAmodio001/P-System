import Lean.Data.Json
import PSystem.QuorumRounds

/-!
# The code the Python node runs

The functions here are compiled into a shared library (`lake build PSystem:shared`) and called
by `network/quorum/lean_core.py`. Each one decodes its argument, calls a definition of the model
(`Rounds.step`, `Rounds.goodProposal`'s `choose`, `Rounds.leader`) and encodes the result. So the
rules of rounds that the theorems of `QuorumRounds` are about are the rules the node executes;
what is outside them is the encoding below and the Python around the call: signatures, storage,
timers and the network. Those are tested, not proved.

Values are event ids (strings); members are numbers below `n`, refused otherwise.
-/

namespace PSystem.Core

open Lean PSystem.Rounds

/-! ## Decoding -/

def member (n : Nat) (j : Json) : Except String (Fin n) := do
  let i ← j.getNat?
  if h : i < n then pure ⟨i, h⟩ else throw s!"member {i} is not below {n}"

def members (n : Nat) (j : Json) : Except String (List (Fin n)) := do
  let a ← j.getArr?
  a.toList.mapM (member n)

def optValue (j : Json) : Except String (Option String) :=
  match j with
  | .null => pure none
  | _ => some <$> j.getStr?

def best (n : Nat) (j : Json) : Except String (Option (Best n String)) :=
  match j with
  | .null => pure none
  | _ => do
      let r ← (← j.getObjVal? "round").getNat?
      let v ← (← j.getObjVal? "value").getStr?
      let s ← members n (← j.getObjVal? "signers")
      pure (some ⟨r, v, s⟩)

def report (n : Nat) (j : Json) : Except String (Report n String) := do
  let v ← optValue (j.getObjValD "vote0")
  let b ← best n (j.getObjValD "best")
  pure ⟨v, b⟩

def roundValue (j : Json) : Except String (Nat × String) := do
  let a ← j.getArr?
  match a.toList with
  | [r, v] => pure (← r.getNat?, ← v.getStr?)
  | _ => throw "expected [round, value]"

def roundReport (n : Nat) (j : Json) : Except String (Nat × Report n String) := do
  let a ← j.getArr?
  match a.toList with
  | [r, rep] => pure (← r.getNat?, ← report n rep)
  | _ => throw "expected [round, report]"

def memberReport (n : Nat) (j : Json) : Except String (Fin n × Report n String) := do
  let m ← member n (← j.getObjVal? "member")
  let rep ← report n j
  pure (m, rep)

def state (n : Nat) (j : Json) : Except String (RState n String) :=
  match j with
  | .null => pure RState.init
  | _ => do
      let round ← (← j.getObjVal? "round").getNat?
      let vote0 ← optValue (j.getObjValD "vote0")
      let prevotes ← (← (← j.getObjVal? "prevotes").getArr?).toList.mapM roundValue
      let b ← best n (j.getObjValD "best")
      let precommits ← (← (← j.getObjVal? "precommits").getArr?).toList.mapM roundValue
      let reports ← (← (← j.getObjVal? "reports").getArr?).toList.mapM (roundReport n)
      let decided ← optValue (j.getObjValD "decided")
      pure ⟨round, vote0, prevotes, b, precommits, reports, decided⟩

def input (n : Nat) (j : Json) : Except String (Input n String) := do
  let kind ← (← j.getObjVal? "kind").getStr?
  let value : Except String String := do (← j.getObjVal? "value").getStr?
  let round : Except String Nat := do (← j.getObjVal? "round").getNat?
  let signers : Except String (List (Fin n)) := do members n (← j.getObjVal? "signers")
  match kind with
  | "request" => pure (.request (← value))
  | "prepared" => pure (.prepared (← round) (← value) (← signers))
  | "timeout" => pure .timeout
  | "proposal" =>
      let reports ← (← (← j.getObjVal? "reports").getArr?).toList.mapM (memberReport n)
      pure (.proposal (← round) (← value) reports)
  | "committed" => pure (.committed (← round) (← value) (← signers))
  | "fast" => pure (.fast (← value) (← signers))
  | other => throw s!"unknown input {other}"

/-! ## Encoding -/

def encMembers {n : Nat} (s : List (Fin n)) : Json := toJson (s.map Fin.val)

def encOpt (v : Option String) : Json := match v with
  | none => .null
  | some s => toJson s

def encBest {n : Nat} (b : Option (Best n String)) : Json := match b with
  | none => .null
  | some b => Json.mkObj [("round", toJson b.round), ("value", toJson b.value),
      ("signers", encMembers b.signers)]

def encReport {n : Nat} (r : Report n String) : Json :=
  Json.mkObj [("vote0", encOpt r.vote0), ("best", encBest r.best)]

def encState {n : Nat} (st : RState n String) : Json :=
  Json.mkObj [
    ("round", toJson st.round),
    ("vote0", encOpt st.vote0),
    ("prevotes", Json.arr (st.prevotes.map fun p => Json.arr #[toJson p.1, toJson p.2]).toArray),
    ("best", encBest st.best),
    ("precommits", Json.arr (st.precommits.map fun p => Json.arr #[toJson p.1, toJson p.2]).toArray),
    ("reports", Json.arr (st.reports.map fun p => Json.arr #[toJson p.1, encReport p.2]).toArray),
    ("decided", encOpt st.decided)]

def answer (r : Except String Json) : String :=
  match r with
  | .ok j => (Json.mkObj [("ok", true), ("result", j)]).compress
  | .error e => (Json.mkObj [("ok", false), ("error", toJson e)]).compress

def committee (j : Json) : Except String (Nat × Nat) := do
  let n ← (← j.getObjVal? "n").getNat?
  let f ← (← j.getObjVal? "f").getNat?
  if n = 3 * f + 1 then pure (n, f) else throw s!"n = {n} is not 3f+1 for f = {f}"

/-! ## What Python calls -/

/-- One transition of `Rounds.step`, for `{"n", "f", "state", "input"}`. -/
def stepJson (request : String) : String := answer do
  let j ← Json.parse request
  let (n, f) ← committee j
  let st ← state n (j.getObjValD "state")
  let x ← input n (← j.getObjVal? "input")
  -- The sender's signature is checked by the caller before it passes a request: every value
  -- that reaches `step` passed it.
  pure (encState (step f (fun _ => true) st x))

/-- The value `Rounds.choose` forces from reports `{"n", "f", "reports"}`, or null. -/
def chooseJson (request : String) : String := answer do
  let j ← Json.parse request
  let (n, f) ← committee j
  let reports ← (← (← j.getObjVal? "reports").getArr?).toList.mapM (memberReport n)
  pure (encOpt (choose f reports))

/-- Whether a proposal is justified, for `{"n", "f", "round", "value", "reports"}`. -/
def justifiedJson (request : String) : String := answer do
  let j ← Json.parse request
  let (n, f) ← committee j
  let r ← (← j.getObjVal? "round").getNat?
  let v ← (← j.getObjVal? "value").getStr?
  let reports ← (← (← j.getObjVal? "reports").getArr?).toList.mapM (memberReport n)
  pure (toJson (justified f r v reports))

/-- The leader of round `r` for a key with offset `k`, for `{"n", "k", "r"}`. -/
def leaderJson (request : String) : String := answer do
  let j ← Json.parse request
  let n ← (← j.getObjVal? "n").getNat?
  let k ← (← j.getObjVal? "k").getNat?
  let r ← (← j.getObjVal? "r").getNat?
  if h : 0 < n then pure (toJson (leader h k r).val) else throw "empty committee"

@[export psystem_rounds_step] def exportStep (s : String) : String := stepJson s
@[export psystem_rounds_choose] def exportChoose (s : String) : String := chooseJson s
@[export psystem_rounds_justified] def exportJustified (s : String) : String := justifiedJson s
@[export psystem_rounds_leader] def exportLeader (s : String) : String := leaderJson s
/-- Takes a string back from the caller, so that the runtime frees it. -/
@[export psystem_release] def exportRelease (_ : String) : UInt8 := 0

end PSystem.Core
