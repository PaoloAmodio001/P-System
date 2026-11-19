import PSystem.Quorum

/-!
# The vote lock and the execution of a certificate, as the node calls them

`Core.lean` exports these to Python. Each one is a definition of the model, applied to what the
caller can hand over: the accounts an event touches, the ids it depends on, and the result of
checking each signature. The theorems below say that this is enough, that is, that on these
arguments the functions answer as `Quorum.step` does on the whole state of the node:

- `step_certificate`: the execution of a certificate in `step` is `executes`, with the signatures
  replaced by the results of checking them;
- `executes_local`: `executes` reads the state only at the sender and the receiver, and the
  executed ids only at the event and its parents;
- `apply_local`, `apply_elsewhere`: `ApplyEvent` on those two accounts gives what it gives on the
  whole state, and changes nothing else;
- `voteAllowed_local`: the vote lock reads only the votes with the same key or the same id.

What is not proved: that Python reads its state and its store into these arguments correctly, that
it checks Ed25519 correctly, and the JSON in between (`docs/PROOF-OBLIGATIONS.md`, "Python and Lean").
-/

namespace PSystem.Core

open PSystem.Quorum

/-- A state given by the rows `(account, balance, nonce)` of some accounts; any other account has
0 of both, as an account never seen has in `core/state.py`. -/
def stateOf (rows : List (Identity × Nat × Nat)) : State where
  balance a := ((rows.find? (fun r => r.1 == a)).map (fun r => r.2.1)).getD 0
  nonce a := ((rows.find? (fun r => r.1 == a)).map (fun r => r.2.2)).getD 0

/-- The rows of the two accounts an event touches, read from a state. -/
def rowsOf (s : State) (e : Event) : List (Identity × Nat × Nat) :=
  [(e.sender, s.balance e.sender, s.nonce e.sender), (e.receiver, s.balance e.receiver, s.nonce e.receiver)]

/-- Those of `ids` among the id of the event and the ids of its parents. -/
def idsOf (ids : List EventId) (e : Event) : List EventId :=
  (e.id :: e.parents).filter (fun x => ids.contains x)

/-- A signature checked by the caller is the result of the check. -/
def checked {n : Nat} : Fin n → Event → Bool → Bool := fun _ _ ok => ok

/-- A certificate with each signature replaced by the result of checking it. -/
def checkedCert {n : Nat} {Sig : Type} (verify : Fin n → Event → Sig → Bool) (c : Cert n Sig) :
    Cert n Bool :=
  ⟨c.event, c.sigs.map fun p => (p.1, verify p.1 c.event p.2)⟩

/-- Whether `Quorum.step` executes a certificate whose signatures were checked. -/
def executes {n : Nat} (q : Nat) (s : State) (ids : List EventId) (c : Cert n Bool) : Bool :=
  certValid checked q c && executableBool s c.event && r17ReadyBool ids c.event &&
    !ids.contains c.event.id

theorem certValid_checked {n : Nat} {Sig : Type} (verify : Fin n → Event → Sig → Bool) (q : Nat)
    (c : Cert n Sig) : certValid checked q (checkedCert verify c) = certValid verify q c := by
  simp [certValid, checkedCert, checked, List.map_map, Function.comp_def, List.all_map]

/-- **The execution in `step` is `executes`.** -/
theorem step_certificate {n : Nat} {Sig : Type} (verify : Fin n → Event → Sig → Bool) (q : Nat)
    (auth : Event → Bool) (st : NodeState n Sig) (c : Cert n Sig) :
    step verify q auth st (.certificate c) =
      if executes q st.state (st.executed.map Event.id) (checkedCert verify c) = true
      then { st with state := ApplyEvent st.state c.event, log := st.log ++ [c] }
      else st := by
  simp only [step, executes, certValid_checked]
  rfl

theorem stateOf_sender (s : State) (e : Event) :
    (stateOf (rowsOf s e)).balance e.sender = s.balance e.sender ∧
      (stateOf (rowsOf s e)).nonce e.sender = s.nonce e.sender := by
  simp [stateOf, rowsOf, List.find?]

theorem stateOf_receiver (s : State) (e : Event) :
    (stateOf (rowsOf s e)).balance e.receiver = s.balance e.receiver ∧
      (stateOf (rowsOf s e)).nonce e.receiver = s.nonce e.receiver := by
  by_cases h : e.sender = e.receiver
  · simp [stateOf, rowsOf, List.find?, h]
  · have h' : (e.sender == e.receiver) = false := by simpa using h
    simp [stateOf, rowsOf, List.find?, h']

theorem executableBool_local (s : State) (e : Event) :
    executableBool (stateOf (rowsOf s e)) e = executableBool s e := by
  simp [executableBool, (stateOf_sender s e).1, (stateOf_sender s e).2]

theorem contains_idsOf (ids : List EventId) (e : Event) {x : EventId} (hx : x ∈ e.id :: e.parents) :
    (idsOf ids e).contains x = ids.contains x := by
  have key : x ∈ idsOf ids e ↔ x ∈ ids := by
    constructor
    · intro hm
      simpa using (List.mem_filter.mp hm).2
    · intro hm
      exact List.mem_filter.mpr ⟨hx, by simpa using hm⟩
  apply Bool.eq_iff_iff.mpr
  simpa using key

theorem r17Ready_local (ids : List EventId) (e : Event) :
    r17ReadyBool (idsOf ids e) e = r17ReadyBool ids e := by
  unfold r17ReadyBool
  apply Bool.eq_iff_iff.mpr
  simp only [List.all_eq_true]
  constructor
  · intro h p hp
    rw [← contains_idsOf ids e (List.mem_cons_of_mem _ hp)]
    exact h p hp
  · intro h p hp
    rw [contains_idsOf ids e (List.mem_cons_of_mem _ hp)]
    exact h p hp

/-- **The state at the two accounts, and the ids of the event and its parents, are enough.** -/
theorem executes_local {n : Nat} (q : Nat) (s : State) (ids : List EventId) (c : Cert n Bool) :
    executes q (stateOf (rowsOf s c.event)) (idsOf ids c.event) c = executes q s ids c := by
  simp only [executes, executableBool_local, r17Ready_local,
    contains_idsOf ids c.event (List.mem_cons_self ..)]

/-- **On the two accounts, applying on their rows gives what applying on the whole state gives.** -/
theorem apply_local (s : State) (e : Event) {a : Identity} (ha : a = e.sender ∨ a = e.receiver) :
    (ApplyEvent (stateOf (rowsOf s e)) e).balance a = (ApplyEvent s e).balance a ∧
      (ApplyEvent (stateOf (rowsOf s e)) e).nonce a = (ApplyEvent s e).nonce a := by
  rcases ha with rfl | rfl
  · simp [ApplyEvent, (stateOf_sender s e).1, (stateOf_sender s e).2]
  · by_cases h : e.receiver = e.sender
    · simp [ApplyEvent, h, (stateOf_sender s e).1, (stateOf_sender s e).2]
    · simp [ApplyEvent, h, (stateOf_receiver s e).1, (stateOf_receiver s e).2]

/-- **And it changes no other account.** -/
theorem apply_elsewhere (s : State) (e : Event) {a : Identity} (hs : a ≠ e.sender)
    (hr : a ≠ e.receiver) : (ApplyEvent s e).balance a = s.balance a ∧
      (ApplyEvent s e).nonce a = s.nonce a := by
  simp [ApplyEvent, hs, hr]

/-- The votes the lock depends on: the same key or the same id. -/
def relevant (e : Event) (v : Event) : Bool :=
  (v.sender == e.sender && v.nonce == e.nonce) || v.id == e.id

/-- **The vote lock reads only the votes with the key or the id of the event.** -/
theorem voteAllowed_local (votes : List Event) (e : Event) :
    voteAllowed (votes.filter (relevant e)) e = voteAllowed votes e := by
  unfold voteAllowed
  rw [List.all_filter]
  apply Bool.eq_iff_iff.mpr
  simp only [List.all_eq_true]
  apply forall_congr'
  intro v
  apply imp_congr_right
  intro _
  cases hr : relevant e v
  · have h1 : (v.sender == e.sender && v.nonce == e.nonce) = false := by
      simp only [relevant, Bool.or_eq_false_iff] at hr
      exact hr.1
    have h2 : (v.id == e.id) = false := by
      simp only [relevant, Bool.or_eq_false_iff] at hr
      exact hr.2
    simp [h1, bne, h2]
  · simp

end PSystem.Core
