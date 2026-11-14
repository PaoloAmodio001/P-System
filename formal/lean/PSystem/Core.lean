import Lean.Data.Json
import PSystem.QuorumRounds
import PSystem.CoreExec

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

/-! ## The vote lock and the execution of a certificate

Arguments are JSON arrays, so that decoding an encoded argument is proved to give it back
(`execRequest_json`, `voteRequest_json`); the strings in between are `Json.compress` and `Json.parse`
of the Lean library, which are trusted. An event is `[id, sender, receiver, amount, nonce, [parents]]`,
with the id a number (the SHA-256 of the event, read as an integer, in Python). -/

open PSystem.Quorum

def eventJson (e : Event) : Json :=
  Json.arr #[toJson e.id, toJson e.sender, toJson e.receiver, toJson e.amount, toJson e.nonce,
    Json.arr (e.parents.map toJson).toArray]

def natList (j : Json) : Except String (List Nat) := do
  let a ← j.getArr?
  a.toList.mapM (·.getNat?)

def event (j : Json) : Except String Event := do
  let a ← j.getArr?
  match a.toList with
  | [i, s, r, amt, k, ps] =>
      pure ⟨← i.getNat?, ← s.getStr?, ← r.getStr?, ← amt.getNat?, ← k.getNat?, ← natList ps⟩
  | _ => throw "expected an event"

def rowJson (r : Identity × Nat × Nat) : Json := Json.arr #[toJson r.1, toJson r.2.1, toJson r.2.2]

def row (j : Json) : Except String (Identity × Nat × Nat) := do
  let a ← j.getArr?
  match a.toList with
  | [acct, b, k] => pure (← acct.getStr?, ← b.getNat?, ← k.getNat?)
  | _ => throw "expected [account, balance, nonce]"

def signerJson {n : Nat} (p : Fin n × Bool) : Json := Json.arr #[toJson p.1.val, toJson p.2]

def signer (n : Nat) (j : Json) : Except String (Fin n × Bool) := do
  let a ← j.getArr?
  match a.toList with
  | [i, ok] => pure (← member n i, ← ok.getBool?)
  | _ => throw "expected [member, checked]"

/-- What `execute` takes: `[n, q, rows, ids, event, signers]`. -/
structure ExecRequest where
  n : Nat
  q : Nat
  rows : List (Identity × Nat × Nat)
  ids : List EventId
  event : Event
  signers : List (Fin n × Bool)

def execRequestJson (x : ExecRequest) : Json :=
  Json.arr #[toJson x.n, toJson x.q, Json.arr (x.rows.map rowJson).toArray,
    Json.arr (x.ids.map toJson).toArray, eventJson x.event,
    Json.arr (x.signers.map signerJson).toArray]

def execRequest (j : Json) : Except String ExecRequest := do
  let a ← j.getArr?
  match a.toList with
  | [n, q, rows, ids, e, sigs] =>
      let n ← n.getNat?
      pure ⟨n, ← q.getNat?, ← (← rows.getArr?).toList.mapM row, ← natList ids, ← event e,
        ← (← sigs.getArr?).toList.mapM (signer n)⟩
  | _ => throw "expected [n, q, rows, ids, event, signers]"

/-- The answer of the model: whether `step` executes, and the two rows after it. -/
def execAnswer (x : ExecRequest) : Json :=
  let s := stateOf x.rows
  let c : Cert x.n Bool := ⟨x.event, x.signers⟩
  let ok := executes x.q s x.ids c
  let after := if ok then ApplyEvent s x.event else s
  Json.mkObj [("executes", toJson ok),
    ("rows", Json.arr ((rowsOf after x.event).map rowJson).toArray)]

def execValue (j : Json) : Except String Json := do
  pure (execAnswer (← execRequest j))

/-- The vote lock: `[[votes], event]`, answered by `Quorum.voteAllowed`. -/
def voteRequestJson (votes : List Event) (e : Event) : Json :=
  Json.arr #[Json.arr (votes.map eventJson).toArray, eventJson e]

def voteRequest (j : Json) : Except String (List Event × Event) := do
  let a ← j.getArr?
  match a.toList with
  | [vs, e] => pure (← (← vs.getArr?).toList.mapM event, ← event e)
  | _ => throw "expected [votes, event]"

def voteValue (j : Json) : Except String Json := do
  let (votes, e) ← voteRequest j
  pure (toJson (voteAllowed votes e))

/-! ### Decoding what was encoded gives it back -/

theorem getNat_toJson (k : Nat) : (toJson k).getNat? = .ok k := rfl
theorem getStr_toJson (s : String) : (toJson s).getStr? = .ok s := rfl
theorem getBool_toJson (b : Bool) : (toJson b).getBool? = .ok b := by cases b <;> rfl

theorem mapM_getNat (ps : List Nat) : ps.mapM ((fun x : Json => x.getNat?) ∘ toJson) = .ok ps := by
  induction ps with
  | nil => rfl
  | cons p ps ih => simp [List.mapM_cons, getNat_toJson, ih]; rfl

theorem natList_json (ps : List Nat) : natList (Json.arr (ps.map toJson).toArray) = .ok ps := by
  simp [natList, Json.getArr?, mapM_getNat]

theorem event_json (e : Event) : event (eventJson e) = .ok e := by
  simp [event, eventJson, Json.getArr?, getNat_toJson, getStr_toJson, natList_json]
  rfl

theorem row_json (r : Identity × Nat × Nat) : row (rowJson r) = .ok r := by
  simp [row, rowJson, Json.getArr?, getNat_toJson, getStr_toJson]
  rfl

theorem member_json {n : Nat} (i : Fin n) : member n (toJson i.val) = .ok i := by
  simp [member, getNat_toJson, bind, Except.bind, i.isLt]
  rfl

theorem signer_json {n : Nat} (p : Fin n × Bool) : signer n (signerJson p) = .ok p := by
  simp [signer, signerJson, Json.getArr?, member_json, getBool_toJson]
  rfl

theorem mapM_of_inverse {α : Type} (dec : Json → Except String α) (enc : α → Json)
    (h : ∀ a, dec (enc a) = .ok a) (l : List α) : l.mapM (dec ∘ enc) = .ok l := by
  induction l with
  | nil => rfl
  | cons a l ih => simp [List.mapM_cons, Function.comp, h, ih]; rfl

theorem execRequest_json (x : ExecRequest) : execRequest (execRequestJson x) = .ok x := by
  cases x
  simp [execRequest, execRequestJson, Json.getArr?, getNat_toJson, natList_json, event_json,
    mapM_of_inverse row rowJson row_json]
  simp only [bind, Except.bind]
  simp [mapM_of_inverse (signer _) signerJson signer_json]
  rfl

theorem voteRequest_json (votes : List Event) (e : Event) :
    voteRequest (voteRequestJson votes e) = .ok (votes, e) := by
  simp [voteRequest, voteRequestJson, Json.getArr?, event_json,
    mapM_of_inverse event eventJson event_json]
  rfl

/-- **On the encoding of any request, `execute` answers the model's answer.** -/
theorem execValue_json (x : ExecRequest) : execValue (execRequestJson x) = .ok (execAnswer x) := by
  simp [execValue, execRequest_json]
  rfl

/-- **On the encoding of any request, `vote_allowed` answers `Quorum.voteAllowed`.** -/
theorem voteValue_json (votes : List Event) (e : Event) :
    voteValue (voteRequestJson votes e) = .ok (toJson (voteAllowed votes e)) := by
  simp [voteValue, voteRequest_json]
  rfl

def executeJson (request : String) : String := answer do execValue (← Json.parse request)
def voteAllowedJson (request : String) : String := answer do voteValue (← Json.parse request)

@[export psystem_execute] def exportExecute (s : String) : String := executeJson s
@[export psystem_vote_allowed] def exportVoteAllowed (s : String) : String := voteAllowedJson s
@[export psystem_rounds_step] def exportStep (s : String) : String := stepJson s
@[export psystem_rounds_choose] def exportChoose (s : String) : String := chooseJson s
@[export psystem_rounds_justified] def exportJustified (s : String) : String := justifiedJson s
@[export psystem_rounds_leader] def exportLeader (s : String) : String := leaderJson s
/-- Takes a string back from the caller, so that the runtime frees it. -/
@[export psystem_release] def exportRelease (_ : String) : UInt8 := 0

end PSystem.Core
