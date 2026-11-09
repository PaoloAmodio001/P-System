import PSystem.QuorumSafety

namespace PSystem.Quorum

/-!
# Thresholds other than `2f+1`, and what a report can and cannot tell

Results on the model, for one committee:

- `no_double_spend_q`: `no_double_spend` with any quorum `q`, under `n + |F| < 2q`.
  `no_double_spend` for `n = 3f+1` and the configuration `n = 5f+1`, `q = 4f+1` are
  both instances. Only safety: `q ≤ n - f`, which liveness needs, is a separate condition.
- `conflict_identifies_faulty`: two valid certificates in conflict name at least
  `2q - n` signers who signed both, and every one of them is faulty. With `n = 3f+1`
  that is `f+1`, which is more than the hypothesis allows.
- `split_lock_ambiguous`: with `n = 4`, `q = 3`, a set of reports of 3 validators can be
  compatible with a certificate for either of two alternatives. So no rule on the
  reports can keep whatever was certified, and unlocking needs `n = 5f+1`.
- `unlock_safe_5f1`: with `n = 5f+1`, `q = 4f+1` and reports from at least `4f+1`
  validators, a certified event has at least `2f+1` reports, and every other event at
  most `2f`. Here a rule on the reports is deterministic.

A report is a value of the model, and honest validators are assumed to report their
vote: `HonestReports` is a hypothesis about a run. The transition that produces a report
is in `QuorumEpochs`.
-/

/-! ## Any quorum -/

theorem delivered_certs_common_voter_q
    {n q : Nat} {Sig : Type}
    (faulty : List (Fin n)) (hq : n + faulty.length < 2 * q)
    (verify : Fin n → Event → Sig → Bool)
    (auth : Fin n → Event → Bool)
    (s₀ : State)
    (inputs : Fin n → List (Input n Sig))
    (hsig : Unforgeable verify faulty q auth s₀ inputs)
    {u v : Fin n} (hu : u ∉ faulty) (hv : v ∉ faulty)
    {c₁ c₂ : Cert n Sig}
    (hin₁ : Input.certificate c₁ ∈ inputs u) (hvalid₁ : certValid verify q c₁ = true)
    (hin₂ : Input.certificate c₂ ∈ inputs v) (hvalid₂ : certValid verify q c₂ = true) :
    ∃ x, x ∉ faulty ∧
      c₁.event ∈ (runNode verify q (auth x) s₀ (inputs x)).votes ∧
      c₂.event ∈ (runNode verify q (auth x) s₀ (inputs x)).votes := by
  simp only [certValid, Bool.and_eq_true, decide_eq_true_eq] at hvalid₁ hvalid₂
  obtain ⟨⟨hnd₁, hq₁⟩, hall₁⟩ := hvalid₁
  obtain ⟨⟨hnd₂, hq₂⟩, hall₂⟩ := hvalid₂
  obtain ⟨x, hx₁, hx₂, hx⟩ := quorum_intersection_honest (F := faulty) hnd₁ hnd₂
    (by simpa using hq₁) (by simpa using hq₂) hq
  obtain ⟨p₁, hp₁, rfl⟩ := List.mem_map.mp hx₁
  obtain ⟨p₂, hp₂, hsame⟩ := List.mem_map.mp hx₂
  refine ⟨p₁.1, hx, hsig u hu c₁ hin₁ p₁ hp₁ hx (List.all_eq_true.mp hall₁ p₁ hp₁), ?_⟩
  have hvotes := hsig v hv c₂ hin₂ p₂ hp₂ (hsame ▸ hx) (List.all_eq_true.mp hall₂ p₂ hp₂)
  rwa [hsame] at hvotes

/--
No double spend for any quorum `q` with `n + |F| < 2q`: two honest nodes, possibly the
same, never execute different events with the same sender and nonce.
-/
theorem no_double_spend_q
    {n q : Nat} {Sig : Type}
    (faulty : List (Fin n)) (hq : n + faulty.length < 2 * q)
    (verify : Fin n → Event → Sig → Bool)
    (auth : Fin n → Event → Bool)
    (s₀ : State)
    (inputs : Fin n → List (Input n Sig))
    (hsig : Unforgeable verify faulty q auth s₀ inputs)
    {u v : Fin n} (hu : u ∉ faulty) (hv : v ∉ faulty)
    {e₁ e₂ : Event}
    (he₁ : e₁ ∈ (runNode verify q (auth u) s₀ (inputs u)).executed)
    (he₂ : e₂ ∈ (runNode verify q (auth v) s₀ (inputs v)).executed)
    (hsender : e₁.sender = e₂.sender) (hnonce : e₁.nonce = e₂.nonce) :
    e₁ = e₂ := by
  obtain ⟨c₁, rfl, hin₁, hvalid₁⟩ := executed_has_cert he₁
  obtain ⟨c₂, rfl, hin₂, hvalid₂⟩ := executed_has_cert he₂
  obtain ⟨x, _, hx₁, hx₂⟩ := delivered_certs_common_voter_q faulty hq verify auth s₀ inputs
    hsig hu hv hin₁ hvalid₁ hin₂ hvalid₂
  exact (voteLock_runNode verify _ (auth x) s₀ (inputs x) _ hx₁ _ hx₂).1 hsender hnonce

/-- The configuration `n = 5f+1`, `q = 4f+1` meets the condition of the theorem. -/
theorem no_double_spend_5f1
    {n f : Nat} {Sig : Type}
    (hn : n = 5 * f + 1)
    (faulty : List (Fin n)) (hf : faulty.length ≤ f)
    (verify : Fin n → Event → Sig → Bool)
    (auth : Fin n → Event → Bool)
    (s₀ : State)
    (inputs : Fin n → List (Input n Sig))
    (hsig : Unforgeable verify faulty (4 * f + 1) auth s₀ inputs)
    {u v : Fin n} (hu : u ∉ faulty) (hv : v ∉ faulty)
    {e₁ e₂ : Event}
    (he₁ : e₁ ∈ (runNode verify (4 * f + 1) (auth u) s₀ (inputs u)).executed)
    (he₂ : e₂ ∈ (runNode verify (4 * f + 1) (auth v) s₀ (inputs v)).executed)
    (hsender : e₁.sender = e₂.sender) (hnonce : e₁.nonce = e₂.nonce) :
    e₁ = e₂ :=
  no_double_spend_q faulty (by omega) verify auth s₀ inputs hsig hu hv he₁ he₂ hsender hnonce

/-! ## Counting -/

/-- Two lists of `Fin n` without duplicates: what `A` shares with `B` is at least
`|A| + |B| - n`. -/
theorem common_length_ge {n : Nat} {A B : List (Fin n)} (hA : A.Nodup) (hB : B.Nodup) :
    A.length + B.length ≤ n + (A.filter fun x => decide (x ∈ B)).length := by
  let inB : Fin n → Bool := fun x => decide (x ∈ B)
  have hnd : ((A.filter fun x => !inB x) ++ B).Nodup := by
    refine List.nodup_append.mpr ⟨List.Nodup.sublist List.filter_sublist hA, hB, ?_⟩
    intro a ha b hb hab
    subst hab
    have := (List.mem_filter.mp ha).2
    simp [inB, hb] at this
  have hfit : ((A.filter fun x => !inB x) ++ B).length ≤ (List.finRange n).length :=
    nodup_length_le_of_subset hnd fun x _ => List.mem_finRange x
  have hsum := length_filter_add_filter_not inB A
  simp only [List.length_append, List.length_finRange] at hfit
  show A.length + B.length ≤ n + (A.filter inB).length
  omega

/-! ## Who is to blame -/

/-- The validators that signed both certificates. It needs only the certificates. -/
def commonSigners {n : Nat} {Sig : Type} (c₁ c₂ : Cert n Sig) : List (Fin n) :=
  (c₁.sigs.map Prod.fst).filter fun x => decide (x ∈ c₂.sigs.map Prod.fst)

/--
From two valid certificates in conflict, delivered to honest nodes: at least `2q - n`
validators signed both, and each of them is in `faulty`. The list comes from the
certificates alone, so anyone can compute it and nobody has to be believed. Note that
nothing bounds `faulty` here: this holds when the hypothesis of the safety theorem fails,
which is the only time two such certificates exist.
-/
theorem conflict_identifies_faulty
    {n q : Nat} {Sig : Type}
    (faulty : List (Fin n))
    (verify : Fin n → Event → Sig → Bool)
    (auth : Fin n → Event → Bool)
    (s₀ : State)
    (inputs : Fin n → List (Input n Sig))
    (hsig : Unforgeable verify faulty q auth s₀ inputs)
    {u v : Fin n} (hu : u ∉ faulty) (hv : v ∉ faulty)
    {c₁ c₂ : Cert n Sig}
    (hin₁ : Input.certificate c₁ ∈ inputs u) (hvalid₁ : certValid verify q c₁ = true)
    (hin₂ : Input.certificate c₂ ∈ inputs v) (hvalid₂ : certValid verify q c₂ = true)
    (hsender : c₁.event.sender = c₂.event.sender) (hnonce : c₁.event.nonce = c₂.event.nonce)
    (hne : c₁.event ≠ c₂.event) :
    (commonSigners c₁ c₂).Nodup ∧
    2 * q ≤ n + (commonSigners c₁ c₂).length ∧
    ∀ x, x ∈ commonSigners c₁ c₂ → x ∈ faulty := by
  simp only [certValid, Bool.and_eq_true, decide_eq_true_eq] at hvalid₁ hvalid₂
  obtain ⟨⟨hnd₁, hq₁⟩, hall₁⟩ := hvalid₁
  obtain ⟨⟨hnd₂, hq₂⟩, hall₂⟩ := hvalid₂
  have hlen₁ : q ≤ (c₁.sigs.map Prod.fst).length := by simpa using hq₁
  have hlen₂ : q ≤ (c₂.sigs.map Prod.fst).length := by simpa using hq₂
  refine ⟨List.Nodup.sublist List.filter_sublist hnd₁, ?_, ?_⟩
  · have := common_length_ge hnd₁ hnd₂
    simp only [commonSigners]
    omega
  · intro x hx
    refine Classical.byContradiction fun hxf => ?_
    obtain ⟨hx₁, hx₂⟩ := List.mem_filter.mp hx
    have hx₂' : x ∈ c₂.sigs.map Prod.fst := by simpa using hx₂
    obtain ⟨p₁, hp₁, rfl⟩ := List.mem_map.mp hx₁
    obtain ⟨p₂, hp₂, hsame⟩ := List.mem_map.mp hx₂'
    have h₁ := hsig u hu c₁ hin₁ p₁ hp₁ hxf (List.all_eq_true.mp hall₁ p₁ hp₁)
    have h₂ := hsig v hv c₂ hin₂ p₂ hp₂ (hsame ▸ hxf) (List.all_eq_true.mp hall₂ p₂ hp₂)
    rw [hsame] at h₂
    exact hne ((voteLock_runNode verify _ (auth p₁.1) s₀ (inputs p₁.1) _ h₁ _ h₂).1
      hsender hnonce)

/-! ## What a report can tell -/

/-- What each validator answered at the end of an epoch, for one `(sender, nonce)`. -/
abbrev Reports (n : Nat) := Fin n → Option Event

/--
A history of one `(sender, nonce)` compatible with some reports: `e` has a certificate,
signed by `signers`; honest validators voted at most once, an honest signer voted for `e`,
and an honest validator that answered reported its vote. A faulty one may report anything,
and any validator may not answer.
-/
structure Compatible {n : Nat} (q f : Nat) (reports : Reports n) (e : Event) : Prop where
  history :
    ∃ (faulty signers : List (Fin n)) (votes : Fin n → Option Event),
      faulty.length ≤ f ∧
      signers.Nodup ∧
      q ≤ signers.length ∧
      (∀ x, x ∈ signers → x ∉ faulty → votes x = some e) ∧
      (∀ x, x ∉ faulty → reports x ≠ none → reports x = votes x)

/-- Reports that fit a certificate for `e`, and one for a different `e'`. -/
def splitReports (e e' : Event) : Reports 4
  | 0 => some e
  | 1 => some e'
  | 2 => some e'
  | 3 => none

theorem fin4_cases : ∀ x : Fin 4, x = 0 ∨ x = 1 ∨ x = 2 ∨ x = 3 := by decide

theorem split_reports_compatible_first (e e' : Event) :
    Compatible 3 1 (splitReports e e') e := by
  refine ⟨[2], [0, 2, 3], fun x => if x = 1 then some e' else some e,
    by decide, by decide, by decide, ?_, ?_⟩
  · intro x hx hxf
    rcases fin4_cases x with rfl | rfl | rfl | rfl
    · simp
    · exact absurd hx (by decide)
    · exact absurd (by decide) hxf
    · simp
  · intro x hxf hne
    rcases fin4_cases x with rfl | rfl | rfl | rfl
    · simp [splitReports]
    · simp [splitReports]
    · exact absurd (by decide) hxf
    · exact absurd rfl hne

theorem split_reports_compatible_second (e e' : Event) :
    Compatible 3 1 (splitReports e e') e' := by
  refine ⟨[], [1, 2, 3], fun x => if x = 0 then some e else some e',
    by decide, by decide, by decide, ?_, ?_⟩
  · intro x hx _
    rcases fin4_cases x with rfl | rfl | rfl | rfl
    · exact absurd hx (by decide)
    · simp
    · simp
    · simp
  · intro x _ hne
    rcases fin4_cases x with rfl | rfl | rfl | rfl
    · simp [splitReports]
    · simp [splitReports]
    · simp [splitReports]
    · exact absurd rfl hne

/--
Constraint 2 of the roadmap. With `n = 4`, `f = 1`, `q = 3`, whatever rule decides from
the reports alone, it cannot return the certified event in every history: the same reports,
from 3 validators, fit a certificate for either alternative. A rule that returns nothing
fails as well, so unlocking is no way out. Hence a conflict at the end of an epoch stays locked.
-/
theorem split_lock_ambiguous (e e' : Event) (hne : e ≠ e') (rule : Reports 4 → Option Event) :
    ¬ ∀ (reports : Reports 4) (certified : Event),
        Compatible 3 1 reports certified → rule reports = some certified := by
  intro hrule
  have h₁ := hrule _ _ (split_reports_compatible_first e e')
  have h₂ := hrule _ _ (split_reports_compatible_second e e')
  rw [h₁] at h₂
  exact hne (Option.some.inj h₂)

/-- The validators among `R` that reported `e`. -/
def reportsFor {n : Nat} (reports : Reports n) (R : List (Fin n)) (e : Event) : List (Fin n) :=
  R.filter fun x => decide (reports x = some e)

/--
With `n = 5f+1` and `q = 4f+1`, take a certificate for `e` and the reports of at least
`4f+1` validators. Honest signers that answered reported `e`. Then `e` has at least `2f+1`
reports, and any other event at most `2f`. So the rule "lock on the event with `2f+1`
reports, unlock if there is none" never loses a certified event and has no choice to make.

This is about one `(sender, nonce)`, one certificate and the reports. That the reports of a
real epoch can be collected with these properties is a separate matter.
-/
theorem unlock_safe_5f1
    {n f : Nat} (hn : n = 5 * f + 1)
    (faulty signers R : List (Fin n)) (hf : faulty.length ≤ f)
    (hS : signers.Nodup) (hSq : 4 * f + 1 ≤ signers.length)
    (hR : R.Nodup) (hRq : 4 * f + 1 ≤ R.length)
    (reports : Reports n) (e : Event)
    (hhonest : ∀ x, x ∈ signers → x ∉ faulty → reports x = none ∨ reports x = some e)
    (hanswered : ∀ x, x ∈ R → reports x ≠ none) :
    2 * f + 1 ≤ (reportsFor reports R e).length ∧
    ∀ e', e' ≠ e → (reportsFor reports (List.finRange n) e').length ≤ 2 * f := by
  let inF : Fin n → Bool := fun x => decide (x ∈ faulty)
  let A := signers.filter fun x => !inF x
  have hAnd : A.Nodup := List.Nodup.sublist List.filter_sublist hS
  -- At least `3f+1` honest signers.
  have hAlen : 3 * f + 1 ≤ A.length := by
    have hsum := length_filter_add_filter_not inF signers
    have hbad : (signers.filter inF).length ≤ faulty.length :=
      nodup_length_le_of_subset (List.Nodup.sublist List.filter_sublist hS) fun x hx => by
        simpa [inF] using (List.mem_filter.mp hx).2
    show 3 * f + 1 ≤ (signers.filter fun x => !inF x).length
    omega
  have hAe : ∀ x, x ∈ A → x ∉ faulty ∧ x ∈ signers := by
    intro x hx
    obtain ⟨h₁, h₂⟩ := List.mem_filter.mp hx
    exact ⟨by simpa [inF] using h₂, h₁⟩
  constructor
  · -- Honest signers that answered reported `e`.
    have hcommon := common_length_ge hAnd hR
    refine Nat.le_trans ?_ (nodup_length_le_of_subset
      (l := A.filter fun x => decide (x ∈ R)) (m := reportsFor reports R e)
      (List.Nodup.sublist List.filter_sublist hAnd) ?_)
    · omega
    · intro x hx
      obtain ⟨hxA, hxR⟩ := List.mem_filter.mp hx
      have hxR' : x ∈ R := by simpa using hxR
      obtain ⟨hxf, hxS⟩ := hAe x hxA
      refine List.mem_filter.mpr ⟨hxR', ?_⟩
      rcases hhonest x hxS hxf with h | h
      · exact absurd h (hanswered x hxR')
      · simpa using h
  · -- Whoever reported another event is outside the honest signers.
    intro e' hne
    have hT : (reportsFor reports (List.finRange n) e').Nodup :=
      List.Nodup.sublist List.filter_sublist (List.nodup_finRange n)
    have hnd : (reportsFor reports (List.finRange n) e' ++ A).Nodup := by
      refine List.nodup_append.mpr ⟨hT, hAnd, ?_⟩
      intro a ha b hb hab
      subst hab
      obtain ⟨hbf, hbS⟩ := hAe a hb
      have hreport : reports a = some e' := by
        simpa using (List.mem_filter.mp ha).2
      rcases hhonest a hbS hbf with h | h <;> rw [hreport] at h
      · cases h
      · exact hne (Option.some.inj h)
    have hfit := nodup_length_le_of_subset hnd fun x _ => List.mem_finRange x
    simp only [List.length_append, List.length_finRange] at hfit
    omega

end PSystem.Quorum
