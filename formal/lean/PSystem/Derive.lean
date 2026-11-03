import PSystem.CausalOrder

namespace PSystem

/-!
# Executable model of `StateDeriver` (core/derive.py)

Phase 1 of the convergence plan: an executable derivation that makes the
same choice as the Python implementation, and the specification that
later phases prove it against.

Python (`StateDeriver._execution_order`), after commit 538ee51: among the
causally ready events, sorted by id, run the first one that is currently
executable; if none is executable, fail. The model below makes exactly
that choice. Differences, to be stated wherever results are used:

- Event ids are `Nat` here and fixed-length SHA-256 hex strings in
  Python. For fixed-length lowercase hex strings the two orders agree.
- Python rejects `amount <= 0` and `sender = receiver` before ordering;
  here such an event is never executable, so the derivation fails as
  well. Both paths reject the batch.
- Python checks conflicts and unknown parents up front; here a conflicting
  or orphaned event is never selected, so the derivation fails as well.
-/

/-! ## Executability as a boolean -/

/-- Boolean version of `Executable`, used by the executable model. -/
def executableBool (s : State) (e : Event) : Bool :=
  decide (e.amount > 0) &&
  decide (e.sender ≠ e.receiver) &&
  decide (s.balance e.sender ≥ e.amount) &&
  decide (s.nonce e.sender = e.nonce)

theorem executableBool_iff (s : State) (e : Event) :
    executableBool s e = true ↔ Executable s e := by
  simp [executableBool, Executable, and_assoc]

/-! ## One step: the Python choice -/

/-- Events that are causally ready and currently executable. -/
def candidates
    (processed : List EventId)
    (s : State)
    (remaining : List Event) : List Event :=
  remaining.filter (fun e => r17ReadyBool processed e && executableBool s e)

/-- The candidate with the smallest id, as chosen by `StateDeriver`. -/
def selectNext
    (processed : List EventId)
    (s : State)
    (remaining : List Event) : Option Event :=
  let c := candidates processed s remaining
  match (c.map Event.id).min? with
  | none => none
  | some m => c.find? (fun x => decide (x.id = m))

theorem mem_candidates_iff
    (processed : List EventId)
    (s : State)
    (remaining : List Event)
    (e : Event) :
    e ∈ candidates processed s remaining ↔
      e ∈ remaining ∧ R17Ready processed e ∧ Executable s e := by
  simp [candidates, r17ReadyBool_iff_R17Ready, executableBool_iff]

/-- A selected event is one of the candidates. -/
theorem selectNext_mem_candidates
    {processed : List EventId}
    {s : State}
    {remaining : List Event}
    {e : Event}
    (h : selectNext processed s remaining = some e) :
    e ∈ candidates processed s remaining := by
  unfold selectNext at h
  dsimp only at h
  cases hmin : ((candidates processed s remaining).map Event.id).min? with
  | none => simp [hmin] at h
  | some m =>
      simp only [hmin] at h
      exact List.mem_of_find?_eq_some h

/--
Specification of one step: the selected event is in `remaining`, causally
ready, executable, and has the smallest id among all such events.
-/
theorem selectNext_spec
    {processed : List EventId}
    {s : State}
    {remaining : List Event}
    {e : Event}
    (h : selectNext processed s remaining = some e) :
    e ∈ remaining ∧ R17Ready processed e ∧ Executable s e ∧
      ∀ other, other ∈ remaining → R17Ready processed other →
        Executable s other → e.id ≤ other.id := by
  have hmem := selectNext_mem_candidates h
  refine ⟨((mem_candidates_iff _ _ _ _).1 hmem).1,
    ((mem_candidates_iff _ _ _ _).1 hmem).2.1,
    ((mem_candidates_iff _ _ _ _).1 hmem).2.2, ?_⟩
  intro other hother hready hexec
  have hotherCand : other ∈ candidates processed s remaining :=
    (mem_candidates_iff _ _ _ _).2 ⟨hother, hready, hexec⟩
  unfold selectNext at h
  dsimp only at h
  cases hmin : ((candidates processed s remaining).map Event.id).min? with
  | none => simp [hmin] at h
  | some m =>
      simp only [hmin] at h
      have hp := List.find?_some h
      have heq : e.id = m := by simpa using hp
      have hle : m ≤ other.id :=
        (List.min?_eq_some_iff.mp hmin).2 other.id
          (List.mem_map.mpr ⟨other, hotherCand, rfl⟩)
      simpa [heq] using hle

/--
`selectNext` fails exactly when no event is both ready and executable.
-/
theorem selectNext_eq_none_iff
    (processed : List EventId)
    (s : State)
    (remaining : List Event) :
    selectNext processed s remaining = none ↔
      ∀ e, e ∈ remaining → R17Ready processed e → ¬ Executable s e := by
  constructor
  · intro h e he hready hexec
    have hcand : e ∈ candidates processed s remaining :=
      (mem_candidates_iff _ _ _ _).2 ⟨he, hready, hexec⟩
    unfold selectNext at h
    dsimp only at h
    cases hmin : ((candidates processed s remaining).map Event.id).min? with
    | none =>
        have hnil := List.min?_eq_none_iff.mp hmin
        have : e.id ∈ (candidates processed s remaining).map Event.id :=
          List.mem_map.mpr ⟨e, hcand, rfl⟩
        simp [hnil] at this
    | some m =>
        simp only [hmin] at h
        have hmMem : m ∈ (candidates processed s remaining).map Event.id :=
          (List.min?_eq_some_iff.mp hmin).1
        obtain ⟨c, hc, hcid⟩ := List.mem_map.mp hmMem
        have hsome :
            ((candidates processed s remaining).find?
              (fun x => decide (x.id = m))).isSome = true :=
          List.find?_isSome.2 ⟨c, hc, by simp [hcid]⟩
        simp [h] at hsome
  · intro h
    cases hsel : selectNext processed s remaining with
    | none => rfl
    | some e =>
        obtain ⟨he, hready, hexec, _⟩ := selectNext_spec hsel
        exact False.elim (h e he hready hexec)

/-! ## The derivation loop -/

/-- Remove every event with the given id (Python: `ready.remove(chosen)`). -/
def dropId (id : EventId) (events : List Event) : List Event :=
  events.filter (fun x => x.id != id)

theorem dropId_length_lt
    {events : List Event} {e : Event} (he : e ∈ events) :
    (dropId e.id events).length < events.length :=
  r17_filter_selected_length_lt events e he

-- `hsel` is used in `decreasing_by`; the unused-variable linter does not see it.
set_option linter.unusedVariables false in
/--
Execution order computed by `StateDeriver`: repeatedly run the selected
event, mark its id as processed, and remove it from `remaining`.
Returns `none` when events remain but none can run.
-/
def executionOrder
    (s : State)
    (processed : List EventId)
    (remaining : List Event) : Option (List Event) :=
  if remaining = [] then
    some []
  else
    match hsel : selectNext processed s remaining with
    | none => none
    | some e =>
        (executionOrder
          (ApplyEvent s e)
          (processed ++ [e.id])
          (dropId e.id remaining)).map (e :: ·)
termination_by remaining.length
decreasing_by
  exact dropId_length_lt (selectNext_spec hsel).1

/-- State derived from an event list, as in `StateDeriver.apply_events`. -/
def derive (s : State) (events : List Event) : Option State :=
  (executionOrder s [] events).map (ApplyEvents s)

/-! ## Specification -/

/-- Every step of the run is executable in the state reached so far. -/
def ExecutableRun : State → List Event → Prop
  | _, [] => True
  | s, e :: rest => Executable s e ∧ ExecutableRun (ApplyEvent s e) rest

/--
A valid execution of `events` from `s`: an ordering of exactly those
events, in which every declared parent runs before its child and every
step is executable.
-/
def ValidExecution (s : State) (events seq : List Event) : Prop :=
  seq.Perm events ∧ ValidSequence events seq ∧ ExecutableRun s seq

end PSystem
