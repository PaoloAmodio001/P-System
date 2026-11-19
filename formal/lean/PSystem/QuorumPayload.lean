import PSystem.QuorumSafety
import PSystem.QuorumRounds

/-!
# Data carried by events (mission records)

Python adds an optional field `data` to an event (`core/event.py`, `docs/MISSION-RECORDS.md`). The
model's `Event` has no such field and is not changed: `data` reaches the model only through the
event id, which in Python is the SHA-256 of the canonical form, and the canonical form includes
`data` when it is not empty.

So the guarantees about data are consequences of the existing theorems, plus one hypothesis on how
ids are made, stated here as `IdBindsData`: an id determines the data it was computed from. For
SHA-256 this is collision resistance, the same kind of assumption as the unforgeability of
signatures, and it is a hypothesis, not a theorem. An encoding that satisfies it exists
(`idBindsData_satisfiable`), so the results are not vacuous.

What is proved, for any type of data `D`:

- `same_id_same_data`: two events with one id carry the same data.
- `certified_data_agree`: two valid certificates delivered to honest nodes, for one
  `(sender, nonce)`, carry the same data (from `delivered_certs_agree`).
- `executed_data_agree`: two honest nodes never execute events with one `(sender, nonce)` and
  different data (from `no_double_spend`).
- `decided_data_agree`: when the decided values of rounds are event ids, two honest validators that
  decide a key decide the same data (from `decisions_agree`).
- `executable_ignores_data`: whether an event can run, and what it does to the state, depend on
  its fields only; so the convergence and derivation theorems hold for events with data as they are.

Not proved here: that Python computes ids as described (tested, `tests/test_mission_records.py`),
and anything about what the data means.
-/

namespace PSystem.Payload

open PSystem PSystem.Quorum

/-- How ids are computed from the fields of an event and its data. -/
structure Encoding (D : Type) where
  idOf : Identity → Identity → Amount → Nonce → List EventId → D → EventId

/-- `e` carries data `d`: its id is the id of its fields with `d`. -/
def Carries {D : Type} (E : Encoding D) (e : Event) (d : D) : Prop :=
  e.id = E.idOf e.sender e.receiver e.amount e.nonce e.parents d

/-- The hypothesis on ids: one id comes from one value of data (collision resistance). -/
def IdBindsData {D : Type} (E : Encoding D) : Prop :=
  ∀ s r a k ps d s' r' a' k' ps' d',
    E.idOf s r a k ps d = E.idOf s' r' a' k' ps' d' → d = d'

/-- An encoding where the hypothesis holds: the id is the data. -/
def trivialEncoding : Encoding Nat := ⟨fun _ _ _ _ _ d => d⟩

theorem idBindsData_satisfiable : IdBindsData trivialEncoding := by
  intro _ _ _ _ _ _ _ _ _ _ _ _ h
  exact h

/-- Two events with one id carry the same data. -/
theorem same_id_same_data {D : Type} {E : Encoding D} (hE : IdBindsData E)
    {e₁ e₂ : Event} {d₁ d₂ : D}
    (h₁ : Carries E e₁ d₁) (h₂ : Carries E e₂ d₂) (hid : e₁.id = e₂.id) : d₁ = d₂ := by
  unfold Carries at h₁ h₂
  exact hE _ _ _ _ _ _ _ _ _ _ _ _ (h₁.symm.trans (hid.trans h₂))

/-- One event carries one value of data. -/
theorem carried_data_unique {D : Type} {E : Encoding D} (hE : IdBindsData E)
    {e : Event} {d₁ d₂ : D} (h₁ : Carries E e d₁) (h₂ : Carries E e d₂) : d₁ = d₂ :=
  same_id_same_data hE h₁ h₂ rfl

/-- Two valid certificates delivered to honest nodes for one `(sender, nonce)` carry the same data. -/
theorem certified_data_agree
    {n f : Nat} {Sig : Type} {D : Type} {E : Encoding D} (hE : IdBindsData E)
    (hn : n = 3 * f + 1)
    (faulty : List (Fin n)) (hf : faulty.length ≤ f)
    (verify : Fin n → Event → Sig → Bool)
    (auth : Fin n → Event → Bool)
    (s₀ : State)
    (inputs : Fin n → List (Input n Sig))
    (hsig : Unforgeable verify faulty (2 * f + 1) auth s₀ inputs)
    {u v : Fin n} (hu : u ∉ faulty) (hv : v ∉ faulty)
    {c₁ c₂ : Cert n Sig}
    (hin₁ : Input.certificate c₁ ∈ inputs u) (hvalid₁ : certValid verify (2 * f + 1) c₁ = true)
    (hin₂ : Input.certificate c₂ ∈ inputs v) (hvalid₂ : certValid verify (2 * f + 1) c₂ = true)
    (hsender : c₁.event.sender = c₂.event.sender) (hnonce : c₁.event.nonce = c₂.event.nonce)
    {d₁ d₂ : D} (h₁ : Carries E c₁.event d₁) (h₂ : Carries E c₂.event d₂) : d₁ = d₂ := by
  have heq := (delivered_certs_agree hn faulty hf verify auth s₀ inputs hsig hu hv
    hin₁ hvalid₁ hin₂ hvalid₂).1 hsender hnonce
  exact same_id_same_data hE h₁ h₂ (congrArg Event.id heq)

/-- Two honest nodes never execute events with one `(sender, nonce)` and different data. -/
theorem executed_data_agree
    {n f : Nat} {Sig : Type} {D : Type} {E : Encoding D} (hE : IdBindsData E)
    (hn : n = 3 * f + 1)
    (faulty : List (Fin n)) (hf : faulty.length ≤ f)
    (verify : Fin n → Event → Sig → Bool)
    (auth : Fin n → Event → Bool)
    (s₀ : State)
    (inputs : Fin n → List (Input n Sig))
    (hsig : Unforgeable verify faulty (2 * f + 1) auth s₀ inputs)
    {u v : Fin n} (hu : u ∉ faulty) (hv : v ∉ faulty)
    {e₁ e₂ : Event}
    (he₁ : e₁ ∈ (runNode verify (2 * f + 1) (auth u) s₀ (inputs u)).executed)
    (he₂ : e₂ ∈ (runNode verify (2 * f + 1) (auth v) s₀ (inputs v)).executed)
    (hsender : e₁.sender = e₂.sender) (hnonce : e₁.nonce = e₂.nonce)
    {d₁ d₂ : D} (h₁ : Carries E e₁ d₁) (h₂ : Carries E e₂ d₂) : d₁ = d₂ := by
  have heq := no_double_spend hn faulty hf verify auth s₀ inputs hsig hu hv he₁ he₂ hsender hnonce
  exact same_id_same_data hE h₁ h₂ (congrArg Event.id heq)

/-- With rounds deciding event ids, two honest validators that decide one key decide the same data. -/
theorem decided_data_agree
    {n f : Nat} {auth : EventId → Bool} {F : List (Fin n)}
    {inputs : Fin n → List (Rounds.Input n EventId)}
    {D : Type} {E : Encoding D} (hE : IdBindsData E)
    (hn : n = 3 * f + 1) (hF : F.length ≤ f) (hU : Rounds.Unforgeable f auth F inputs)
    {u u' : Fin n} (hu : u ∉ F) (hu' : u' ∉ F) {e₁ e₂ : Event}
    (hv : (Rounds.final f auth inputs u).decided = some e₁.id)
    (hw : (Rounds.final f auth inputs u').decided = some e₂.id)
    {d₁ d₂ : D} (h₁ : Carries E e₁ d₁) (h₂ : Carries E e₂ d₂) : d₁ = d₂ :=
  same_id_same_data hE h₁ h₂ (Rounds.decisions_agree hn hF hU hu hu' hv hw)

/-- Whether an event runs, and its effect, depend only on its fields: data has no part in them. -/
theorem executable_ignores_data {D : Type} (E : Encoding D) (s : State) (e : Event) (d : D)
    (_h : Carries E e d) :
    (Executable s e ↔ (e.amount > 0 ∧ e.sender ≠ e.receiver ∧ s.balance e.sender ≥ e.amount ∧
      s.nonce e.sender = e.nonce)) ∧
    ApplyEvent s e = ApplyEvent s { e with id := e.id } := by
  exact ⟨Iff.rfl, rfl⟩

end PSystem.Payload
