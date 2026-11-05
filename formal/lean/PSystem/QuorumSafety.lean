import PSystem.Quorum

namespace PSystem.Quorum

/-!
# No double spend across honest nodes (obligation O7)

Main result:

- `no_double_spend`: with `n = 3f+1` validators, at most `f` of them faulty,
  quorum `2f+1` and unforgeable signatures, two honest nodes, possibly the
  same one, never execute different events with the same `(sender, nonce)`.

Each node has its own arbitrary list of inputs. No hypothesis says that
honest nodes see the same messages, and nothing constrains faulty nodes:
they can sign both alternatives and show each node something different.

Method, as in FastPay (Lemma A.1): the signers of two certificates share an
honest validator, by counting (`quorum_intersection_honest`). Unforgeability
turns its two signatures into two real votes (`common_honest_voter`), and the
vote lock (`voteLock_runNode`) says that the two votes are for one event.

`same_id_same_event` is the same argument for event ids. It replaces a
collision-resistance hypothesis and is what `derive` will need (distinct ids).
-/

/-! ## Counting -/

/-- A list without duplicates is no longer than any list containing it. -/
theorem nodup_length_le_of_subset {α : Type} [DecidableEq α] :
    ∀ {l m : List α}, l.Nodup → (∀ x, x ∈ l → x ∈ m) → l.length ≤ m.length
  | [], _, _, _ => by simp
  | a :: t, m, hnd, hsub => by
      obtain ⟨hat, hndt⟩ := List.nodup_cons.mp hnd
      have ha : a ∈ m := hsub a (by simp)
      have ih : t.length ≤ (m.erase a).length :=
        nodup_length_le_of_subset hndt fun x hx =>
          (List.mem_erase_of_ne fun (h : x = a) => hat (h ▸ hx)).2
            (hsub x (List.mem_cons_of_mem a hx))
      have hlen := List.length_erase_of_mem ha
      have hpos := List.length_pos_of_mem ha
      simp only [List.length_cons]
      omega

theorem length_filter_add_filter_not {α : Type} (p : α → Bool) (l : List α) :
    (l.filter p).length + (l.filter fun x => !p x).length = l.length := by
  induction l with
  | nil => rfl
  | cons x xs ih =>
      cases hp : p x <;> simp [hp] <;> omega

/--
Quorum intersection: two sets of at least `q` validators out of `n` contain a
common validator outside `F`, whenever `n + |F| < 2q`. With `n = 3f+1`,
`q = 2f+1` and `|F| ≤ f` the condition holds: the margin is exactly one.
`F` may contain duplicates, which only make the condition harder to meet.
-/
theorem quorum_intersection_honest {n q : Nat} {A B F : List (Fin n)}
    (hA : A.Nodup) (hB : B.Nodup)
    (hAq : q ≤ A.length) (hBq : q ≤ B.length)
    (hq : n + F.length < 2 * q) :
    ∃ x, x ∈ A ∧ x ∈ B ∧ x ∉ F := by
  refine Classical.byContradiction fun hno => ?_
  let inF : Fin n → Bool := fun x => decide (x ∈ F)
  -- Signers of `A` in `F` are at most `|F|`.
  have hAF : (A.filter inF).length ≤ F.length :=
    nodup_length_le_of_subset (List.Nodup.sublist List.filter_sublist hA) fun x hx => by
      simpa [inF] using (List.mem_filter.mp hx).2
  -- The others are disjoint from `B`, so together they fit in `Fin n`.
  have hnd : ((A.filter fun x => !inF x) ++ B).Nodup := by
    refine List.nodup_append.mpr
      ⟨List.Nodup.sublist List.filter_sublist hA, hB, ?_⟩
    intro a ha b hb hab
    subst hab
    obtain ⟨haA, haF⟩ := List.mem_filter.mp ha
    exact hno ⟨a, haA, hb, by simpa [inF] using haF⟩
  have hfit : ((A.filter fun x => !inF x) ++ B).length ≤ (List.finRange n).length :=
    nodup_length_le_of_subset hnd fun x _ => List.mem_finRange x
  have hsum := length_filter_add_filter_not inF A
  simp only [List.length_append, List.length_finRange] at hfit
  omega

/-! ## Local invariants of an honest node -/

/-- No two different votes share a `(sender, nonce)` or an id. -/
def VoteLock (votes : List Event) : Prop :=
  ∀ a, a ∈ votes → ∀ b, b ∈ votes →
    (a.sender = b.sender → a.nonce = b.nonce → a = b) ∧ (a.id = b.id → a = b)

/-- What `voteAllowed` says about each earlier vote. -/
theorem voteAllowed_spec {votes : List Event} {e : Event}
    (h : voteAllowed votes e = true) {a : Event} (ha : a ∈ votes) :
    (a.sender = e.sender → a.nonce = e.nonce → a = e) ∧ (a.id = e.id → a = e) := by
  have hall := (List.all_eq_true.mp h) a ha
  by_cases hae : a = e
  · exact ⟨fun _ _ => hae, fun _ => hae⟩
  · simp only [Bool.or_eq_true, beq_iff_eq, hae, false_or, Bool.and_eq_true,
      Bool.not_eq_true', Bool.and_eq_false_iff, bne_iff_ne, ne_eq,
      beq_eq_false_iff_ne] at hall
    obtain ⟨hkey, hid⟩ := hall
    refine ⟨fun hs hn => ?_, fun hi => absurd hi hid⟩
    cases hkey with
    | inl h => exact absurd hs h
    | inr h => exact absurd hn h

/-- A step keeps the lock: this is where an honest validator differs from a faulty one. -/
theorem voteLock_step {n Sig} (verify : Fin n → Event → Sig → Bool) (q : Nat)
    (auth : Event → Bool) (st : NodeState n Sig) (i : Input n Sig)
    (h : VoteLock st.votes) : VoteLock (step verify q auth st i).votes := by
  cases i with
  | voteRequest e =>
      simp only [step]
      split
      · rename_i hif
        have hallowed : voteAllowed st.votes e = true :=
          (Bool.and_eq_true_iff.mp hif).2
        intro a ha b hb
        simp only [List.mem_cons] at ha hb
        rcases ha with rfl | ha <;> rcases hb with rfl | hb
        · exact ⟨fun _ _ => rfl, fun _ => rfl⟩
        · have hs := voteAllowed_spec hallowed hb
          exact ⟨fun h₁ h₂ => (hs.1 h₁.symm h₂.symm).symm, fun h₁ => (hs.2 h₁.symm).symm⟩
        · exact voteAllowed_spec hallowed ha
        · exact h a ha b hb
      · exact h
  | certificate c =>
      simp only [step]
      split <;> exact h

theorem voteLock_foldl {n Sig} (verify : Fin n → Event → Sig → Bool) (q : Nat)
    (auth : Event → Bool) (inputs : List (Input n Sig)) (st : NodeState n Sig)
    (h : VoteLock st.votes) :
    VoteLock (inputs.foldl (step verify q auth) st).votes := by
  induction inputs generalizing st with
  | nil => exact h
  | cons i rest ih => exact ih _ (voteLock_step verify q auth st i h)

/-- The votes of an honest node satisfy the lock, whatever it received. -/
theorem voteLock_runNode {n Sig} (verify : Fin n → Event → Sig → Bool) (q : Nat)
    (auth : Event → Bool) (s₀ : State) (inputs : List (Input n Sig)) :
    VoteLock (runNode verify q auth s₀ inputs).votes :=
  voteLock_foldl verify q auth inputs _ (by intro a ha; simp at ha)

/-- A certificate in the log was delivered and valid, or was already there. -/
theorem log_foldl {n Sig} (verify : Fin n → Event → Sig → Bool) (q : Nat)
    (auth : Event → Bool) (inputs : List (Input n Sig)) (st : NodeState n Sig)
    {c : Cert n Sig} (hc : c ∈ (inputs.foldl (step verify q auth) st).log) :
    c ∈ st.log ∨ (Input.certificate c ∈ inputs ∧ certValid verify q c = true) := by
  induction inputs generalizing st with
  | nil => exact Or.inl hc
  | cons i rest ih =>
      rcases ih _ hc with hstep | ⟨hmem, hvalid⟩
      · cases i with
        | voteRequest e =>
            simp only [step] at hstep
            split at hstep <;> exact Or.inl hstep
        | certificate c' =>
            simp only [step] at hstep
            split at hstep
            · rename_i hif
              simp only [List.mem_append, List.mem_singleton] at hstep
              rcases hstep with hold | rfl
              · exact Or.inl hold
              · have hvalid : certValid verify q c = true := by
                  simp only [Bool.and_eq_true] at hif
                  exact hif.1.1.1
                exact Or.inr ⟨List.mem_cons_self, hvalid⟩
            · exact Or.inl hstep
      · exact Or.inr ⟨List.mem_cons_of_mem i hmem, hvalid⟩

/-- An executed event comes from a valid certificate delivered to that node. -/
theorem executed_has_cert {n Sig} {verify : Fin n → Event → Sig → Bool} {q : Nat}
    {auth : Event → Bool} {s₀ : State} {inputs : List (Input n Sig)} {e : Event}
    (he : e ∈ (runNode verify q auth s₀ inputs).executed) :
    ∃ c : Cert n Sig, c.event = e ∧ Input.certificate c ∈ inputs ∧
      certValid verify q c = true := by
  obtain ⟨c, hc, rfl⟩ := List.mem_map.mp he
  rcases log_foldl verify q auth inputs _ hc with hempty | ⟨hmem, hvalid⟩
  · simp at hempty
  · exact ⟨c, rfl, hmem, hvalid⟩

/-! ## Across nodes -/

/--
Two valid certificates delivered to honest nodes have a common honest validator
that voted for both events. This is the only place where the hypotheses about
`n`, `f` and signatures are used, and where a fact about one node's inputs
reaches another.
-/
theorem delivered_certs_common_voter
    {n f : Nat} {Sig : Type}
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
    (hin₂ : Input.certificate c₂ ∈ inputs v) (hvalid₂ : certValid verify (2 * f + 1) c₂ = true) :
    ∃ x, x ∉ faulty ∧
      c₁.event ∈ (runNode verify (2 * f + 1) (auth x) s₀ (inputs x)).votes ∧
      c₂.event ∈ (runNode verify (2 * f + 1) (auth x) s₀ (inputs x)).votes := by
  simp only [certValid, Bool.and_eq_true, decide_eq_true_eq] at hvalid₁ hvalid₂
  obtain ⟨⟨hnd₁, hq₁⟩, hall₁⟩ := hvalid₁
  obtain ⟨⟨hnd₂, hq₂⟩, hall₂⟩ := hvalid₂
  obtain ⟨x, hx₁, hx₂, hx⟩ := quorum_intersection_honest (F := faulty) hnd₁ hnd₂
    (by simpa using hq₁) (by simpa using hq₂) (by omega)
  obtain ⟨p₁, hp₁, rfl⟩ := List.mem_map.mp hx₁
  obtain ⟨p₂, hp₂, hsame⟩ := List.mem_map.mp hx₂
  refine ⟨p₁.1, hx, hsig u hu c₁ hin₁ p₁ hp₁ hx (List.all_eq_true.mp hall₁ p₁ hp₁), ?_⟩
  have hvotes := hsig v hv c₂ hin₂ p₂ hp₂ (hsame ▸ hx) (List.all_eq_true.mp hall₂ p₂ hp₂)
  rwa [hsame] at hvotes

/--
Two valid certificates delivered to honest nodes, even if not executed, are for
the same event when they share `(sender, nonce)` or id. So a node that holds two
valid certificates in conflict has evidence that the hypotheses do not hold:
it can stop, because this cannot happen with at most `f` faults.
-/
theorem delivered_certs_agree
    {n f : Nat} {Sig : Type}
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
    (hin₂ : Input.certificate c₂ ∈ inputs v) (hvalid₂ : certValid verify (2 * f + 1) c₂ = true) :
    (c₁.event.sender = c₂.event.sender → c₁.event.nonce = c₂.event.nonce → c₁.event = c₂.event) ∧
    (c₁.event.id = c₂.event.id → c₁.event = c₂.event) := by
  obtain ⟨x, _, hx₁, hx₂⟩ := delivered_certs_common_voter hn faulty hf verify auth s₀ inputs hsig
    hu hv hin₁ hvalid₁ hin₂ hvalid₂
  exact voteLock_runNode verify _ (auth x) s₀ (inputs x) _ hx₁ _ hx₂

/--
Events executed by two honest nodes have a common honest validator that voted
for both.
-/
theorem common_honest_voter
    {n f : Nat} {Sig : Type}
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
    (he₂ : e₂ ∈ (runNode verify (2 * f + 1) (auth v) s₀ (inputs v)).executed) :
    ∃ x, x ∉ faulty ∧ e₁ ∈ (runNode verify (2 * f + 1) (auth x) s₀ (inputs x)).votes ∧
      e₂ ∈ (runNode verify (2 * f + 1) (auth x) s₀ (inputs x)).votes := by
  obtain ⟨c₁, rfl, hin₁, hvalid₁⟩ := executed_has_cert he₁
  obtain ⟨c₂, rfl, hin₂, hvalid₂⟩ := executed_has_cert he₂
  exact delivered_certs_common_voter hn faulty hf verify auth s₀ inputs hsig hu hv
    hin₁ hvalid₁ hin₂ hvalid₂

/--
No double spend. Two honest nodes, possibly the same, never execute different
events with the same sender and nonce.

No hypothesis says that the nodes see the same messages: `inputs` is arbitrary
and each node has its own list. Faulty validators may sign anything.
-/
theorem no_double_spend
    {n f : Nat} {Sig : Type}
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
    (hsender : e₁.sender = e₂.sender) (hnonce : e₁.nonce = e₂.nonce) :
    e₁ = e₂ := by
  obtain ⟨x, _, hx₁, hx₂⟩ :=
    common_honest_voter hn faulty hf verify auth s₀ inputs hsig hu hv he₁ he₂
  exact (voteLock_runNode verify _ (auth x) s₀ (inputs x) e₁ hx₁ e₂ hx₂).1 hsender hnonce

/--
Two events executed by honest nodes with the same id are the same event, with
no collision-resistance hypothesis: an honest validator also locks on the id.
-/
theorem same_id_same_event
    {n f : Nat} {Sig : Type}
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
    (hid : e₁.id = e₂.id) :
    e₁ = e₂ := by
  obtain ⟨x, _, hx₁, hx₂⟩ :=
    common_honest_voter hn faulty hf verify auth s₀ inputs hsig hu hv he₁ he₂
  exact (voteLock_runNode verify _ (auth x) s₀ (inputs x) e₁ hx₁ e₂ hx₂).2 hid

/-! ## Authorization -/

theorem votes_authorized_foldl {n : Nat} {Sig : Type} (verify : Fin n → Event → Sig → Bool)
    (q : Nat) (auth : Event → Bool) (inputs : List (Input n Sig)) (st : NodeState n Sig)
    {e : Event} (he : e ∈ (inputs.foldl (step verify q auth) st).votes) :
    e ∈ st.votes ∨ auth e = true := by
  induction inputs generalizing st with
  | nil => exact Or.inl he
  | cons i rest ih =>
      rcases ih _ he with hstep | hauth
      · cases i with
        | voteRequest e' =>
            simp only [step] at hstep
            split at hstep
            · rename_i hif
              simp only [List.mem_cons] at hstep
              rcases hstep with rfl | hold
              · exact Or.inr (Bool.and_eq_true_iff.mp hif).1
              · exact Or.inl hold
            · exact Or.inl hstep
        | certificate c =>
            simp only [step] at hstep
            split at hstep <;> exact Or.inl hstep
      · exact Or.inr hauth

/-- An honest validator only votes for events that its own check accepts. -/
theorem votes_authorized {n : Nat} {Sig : Type} (verify : Fin n → Event → Sig → Bool)
    (q : Nat) (auth : Event → Bool) (s₀ : State) (inputs : List (Input n Sig)) {e : Event}
    (he : e ∈ (runNode verify q auth s₀ inputs).votes) : auth e = true := by
  rcases votes_authorized_foldl verify q auth inputs _ he with hempty | hauth
  · simp at hempty
  · exact hauth

/--
An event executed by an honest node was accepted by the check `auth` of at least
one honest validator. `auth` is abstract: this says nothing about Ed25519 by
itself, and what it gives depends on what the check verifies.
-/
theorem executed_authorized
    {n f : Nat} {Sig : Type}
    (hn : n = 3 * f + 1)
    (faulty : List (Fin n)) (hf : faulty.length ≤ f)
    (verify : Fin n → Event → Sig → Bool)
    (auth : Fin n → Event → Bool)
    (s₀ : State)
    (inputs : Fin n → List (Input n Sig))
    (hsig : Unforgeable verify faulty (2 * f + 1) auth s₀ inputs)
    {u : Fin n} (hu : u ∉ faulty) {e : Event}
    (he : e ∈ (runNode verify (2 * f + 1) (auth u) s₀ (inputs u)).executed) :
    ∃ x, x ∉ faulty ∧ auth x e = true := by
  obtain ⟨c, rfl, hin, hvalid⟩ := executed_has_cert he
  obtain ⟨x, hx, hvote, _⟩ := delivered_certs_common_voter hn faulty hf verify auth s₀ inputs hsig
    hu hu hin hvalid hin hvalid
  exact ⟨x, hx, votes_authorized verify _ (auth x) s₀ (inputs x) hvote⟩

end PSystem.Quorum
