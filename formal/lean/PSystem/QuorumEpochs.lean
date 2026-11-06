import PSystem.QuorumThresholds

namespace PSystem.Quorum

/-!
# A chain of committees (phase B of `ROADMAP.md`)

The standard configuration of decision D2: no unlocking. At the end of an epoch each
validator of a quorum reports what it voted for and stops voting. The union of the reports,
carried over from every earlier epoch, is the list of locks of the next epoch. A validator
votes for `e` only if every lock on its `(sender, nonce)` is `e`:

- no lock: nobody can hold a certificate for that `(sender, nonce)` from before;
- one alternative: an honest sender with incomplete votes finishes by sending it again;
- two alternatives: the account stays locked for that nonce, for good. This is the price
  stated in D2, and `split_lock_ambiguous` shows that no rule on the reports can avoid it.

Main results:

- `no_double_spend_across_epochs`: no two different events with one `(sender, nonce)` have
  a certificate, in any two epochs, the same or different;
- `closure_preserves_certified`: what has a certificate in an epoch is in the locks of the
  next one, whichever quorum reported and whatever faulty validators reported;
- `locks_carried`: a lock stays in every later epoch;
Limits, to be stated wherever these are used:

- Each committee needs its own bound on faulty validators, as a hypothesis. It is what the
  governance of D1 has to choose well, and it is an assumption of trust, not a theorem.
- `Certified` includes unforgeability: an honest signer really voted. Signatures are not
  modelled here, as in `Unforgeable`.
- That reports reach the next committee is `ChainValid`, a hypothesis about the run.
  Nothing here says that a closure is ever reached: this is safety, not liveness.
- A faulty validator can report an event nobody signed. That adds a lock and can only block
  a nonce. Python checks the signature of the sender on each reported event.
-/

/-- What a validator can receive in an epoch. -/
inductive EpochInput where
  | voteRequest (e : Event)
  | close
  deriving DecidableEq

structure EpochNode where
  votes  : List Event
  closed : Bool

/-- Every lock on the `(sender, nonce)` of `e` is `e`. -/
def lockAllows (locks : List Event) (e : Event) : Bool :=
  locks.all fun l => !(l.sender == e.sender && l.nonce == e.nonce) || l == e

/-- One step of a validator. After `close` it votes for nothing. -/
def epochStep (locks : List Event) (auth : Event → Bool) (st : EpochNode) :
    EpochInput → EpochNode
  | .voteRequest e =>
      if !st.closed && auth e && lockAllows locks e && voteAllowed st.votes e
      then { st with votes := e :: st.votes } else st
  | .close => { st with closed := true }

def runEpoch (locks : List Event) (auth : Event → Bool) (inputs : List EpochInput) : EpochNode :=
  inputs.foldl (epochStep locks auth) { votes := [], closed := false }

/-- What a validator reports: its votes at its first `close`. -/
def reportOf (locks : List Event) (auth : Event → Bool) (inputs : List EpochInput) : List Event :=
  (runEpoch locks auth (inputs.takeWhile (· != .close))).votes

/-- One epoch: a committee, who is faulty in it, what its validators received, and which
validators reported for its closure. -/
structure Epoch where
  n : Nat
  q : Nat
  faulty : List (Fin n)
  auth : Fin n → Event → Bool
  inputs : Fin n → List EpochInput
  reporters : List (Fin n)
  safe : n + faulty.length < 2 * q
  reportersNodup : reporters.Nodup
  reportersQuorum : q ≤ reporters.length

/-- The votes of a validator in an epoch, under the locks of that epoch. -/
def Epoch.votes (E : Epoch) (locks : List Event) (x : Fin E.n) : List Event :=
  (runEpoch locks (E.auth x) (E.inputs x)).votes

/-- A certificate for `e` in this epoch: a quorum of distinct signers, and each honest one
really voted for `e`. -/
def Certified (E : Epoch) (locks : List Event) (e : Event) : Prop :=
  ∃ signers : List (Fin E.n), signers.Nodup ∧ E.q ≤ signers.length ∧
    ∀ x, x ∈ signers → x ∉ E.faulty → e ∈ E.votes locks x

/-- How epochs follow each other: locks only grow, and each honest reporter closed and has
its report in the locks of the next epoch. -/
def ChainValid (E : Nat → Epoch) (locks : Nat → List Event) : Prop :=
  ∀ k,
    (∀ e, e ∈ locks k → e ∈ locks (k + 1)) ∧
    ∀ x, x ∈ (E k).reporters → x ∉ (E k).faulty →
      EpochInput.close ∈ (E k).inputs x ∧
      ∀ e, e ∈ reportOf (locks k) ((E k).auth x) ((E k).inputs x) → e ∈ locks (k + 1)

/-! ## One validator -/

theorem epoch_voteLock_step (locks : List Event) (auth : Event → Bool) (st : EpochNode)
    (i : EpochInput) (h : VoteLock st.votes) :
    VoteLock (epochStep locks auth st i).votes := by
  cases i with
  | close => exact h
  | voteRequest e =>
      simp only [epochStep]
      split
      · rename_i hif
        have hallowed : voteAllowed st.votes e = true := (Bool.and_eq_true_iff.mp hif).2
        intro a ha b hb
        simp only [List.mem_cons] at ha hb
        rcases ha with rfl | ha <;> rcases hb with rfl | hb
        · exact ⟨fun _ _ => rfl, fun _ => rfl⟩
        · have hs := voteAllowed_spec hallowed hb
          exact ⟨fun h₁ h₂ => (hs.1 h₁.symm h₂.symm).symm, fun h₁ => (hs.2 h₁.symm).symm⟩
        · exact voteAllowed_spec hallowed ha
        · exact h a ha b hb
      · exact h

theorem epoch_voteLock_foldl (locks : List Event) (auth : Event → Bool)
    (inputs : List EpochInput) (st : EpochNode) (h : VoteLock st.votes) :
    VoteLock (inputs.foldl (epochStep locks auth) st).votes := by
  induction inputs generalizing st with
  | nil => exact h
  | cons i rest ih => exact ih _ (epoch_voteLock_step locks auth st i h)

/-- The votes of an honest validator in an epoch satisfy the lock. -/
theorem epoch_voteLock (locks : List Event) (auth : Event → Bool) (inputs : List EpochInput) :
    VoteLock (runEpoch locks auth inputs).votes :=
  epoch_voteLock_foldl locks auth inputs _ (by intro a ha; simp at ha)

/-- Every vote respects the locks. -/
theorem votes_respect_locks_foldl (locks : List Event) (auth : Event → Bool)
    (inputs : List EpochInput) (st : EpochNode) {e : Event}
    (he : e ∈ (inputs.foldl (epochStep locks auth) st).votes) :
    e ∈ st.votes ∨ lockAllows locks e = true := by
  induction inputs generalizing st with
  | nil => exact Or.inl he
  | cons i rest ih =>
      rcases ih _ he with hstep | hallow
      · cases i with
        | close => exact Or.inl hstep
        | voteRequest e' =>
            simp only [epochStep] at hstep
            split at hstep
            · rename_i hif
              rcases List.mem_cons.mp hstep with rfl | hold
              · have h := (Bool.and_eq_true_iff.mp (Bool.and_eq_true_iff.mp hif).1).2
                exact Or.inr h
              · exact Or.inl hold
            · exact Or.inl hstep
      · exact Or.inr hallow

theorem votes_respect_locks (locks : List Event) (auth : Event → Bool)
    (inputs : List EpochInput) {e : Event} (he : e ∈ (runEpoch locks auth inputs).votes) :
    lockAllows locks e = true := by
  rcases votes_respect_locks_foldl locks auth inputs _ he with h | h
  · simp at h
  · exact h

/-- What `lockAllows` means for one lock. -/
theorem lockAllows_spec {locks : List Event} {e l : Event} (h : lockAllows locks e = true)
    (hl : l ∈ locks) (hs : l.sender = e.sender) (hn : l.nonce = e.nonce) : l = e := by
  have := List.all_eq_true.mp h l hl
  simpa [hs, hn] using this

/-- A closed validator votes for nothing more. -/
theorem votes_stable_once_closed (locks : List Event) (auth : Event → Bool)
    (inputs : List EpochInput) (st : EpochNode) (hc : st.closed = true) :
    (inputs.foldl (epochStep locks auth) st).votes = st.votes := by
  induction inputs generalizing st with
  | nil => rfl
  | cons i rest ih =>
      have hnext : epochStep locks auth st i = st ∨
          epochStep locks auth st i = { st with closed := true } := by
        cases i with
        | close => exact Or.inr rfl
        | voteRequest e =>
            left
            simp [epochStep, hc]
      simp only [List.foldl_cons]
      rcases hnext with h | h
      · rw [h]; exact ih st hc
      · rw [h]; exact ih { st with closed := true } rfl

/-- `close` is the input after the part `takeWhile` keeps. -/
theorem split_at_close {inputs : List EpochInput} (h : EpochInput.close ∈ inputs) :
    ∃ rest, inputs = inputs.takeWhile (· != .close) ++ EpochInput.close :: rest := by
  induction inputs with
  | nil => simp at h
  | cons i tail ih =>
      by_cases hi : i = EpochInput.close
      · subst hi
        exact ⟨tail, by simp⟩
      · have htail : EpochInput.close ∈ tail := by
          rcases List.mem_cons.mp h with h | h
          · exact absurd h.symm hi
          · exact h
        obtain ⟨rest, hrest⟩ := ih htail
        refine ⟨rest, ?_⟩
        have hne : (i != EpochInput.close) = true := by simpa using hi
        simp only [List.takeWhile_cons, hne, ite_true, List.cons_append]
        exact congrArg (i :: ·) hrest

/-- A report holds every vote of the validator, including the ones it could still receive. -/
theorem report_holds_every_vote (locks : List Event) (auth : Event → Bool)
    {inputs : List EpochInput} (h : EpochInput.close ∈ inputs) :
    (runEpoch locks auth inputs).votes = reportOf locks auth inputs := by
  obtain ⟨rest, hrest⟩ := split_at_close h
  have hsplit : ∀ pre, inputs = pre ++ EpochInput.close :: rest → runEpoch locks auth inputs =
      (EpochInput.close :: rest).foldl (epochStep locks auth) (runEpoch locks auth pre) := by
    intro pre hpre
    rw [hpre]
    simp only [runEpoch, List.foldl_append]
  have hfold := hsplit _ hrest
  rw [hfold, reportOf]
  simp only [List.foldl_cons]
  exact votes_stable_once_closed locks auth rest _ rfl

/-! ## One epoch -/

/-- Two certificates in one epoch have a common honest voter, so they agree. -/
theorem certified_same_epoch {E : Epoch} {locks : List Event} {e₁ e₂ : Event}
    (h₁ : Certified E locks e₁) (h₂ : Certified E locks e₂)
    (hs : e₁.sender = e₂.sender) (hn : e₁.nonce = e₂.nonce) : e₁ = e₂ := by
  obtain ⟨S₁, hnd₁, hq₁, hv₁⟩ := h₁
  obtain ⟨S₂, hnd₂, hq₂, hv₂⟩ := h₂
  obtain ⟨x, hx₁, hx₂, hx⟩ := quorum_intersection_honest hnd₁ hnd₂ hq₁ hq₂ E.safe
  exact (epoch_voteLock locks (E.auth x) (E.inputs x) _ (hv₁ x hx₁ hx) _ (hv₂ x hx₂ hx)).1 hs hn

/-- The quorum exceeds the faulty validators, so a certificate has an honest signer. -/
theorem certified_has_honest_voter {E : Epoch} {locks : List Event} {e : Event}
    (h : Certified E locks e) : ∃ x, x ∉ E.faulty ∧ e ∈ E.votes locks x := by
  obtain ⟨S, hnd, hq, hv⟩ := h
  obtain ⟨x, hx₁, _, hx⟩ := quorum_intersection_honest hnd hnd hq hq E.safe
  exact ⟨x, hx, hv x hx₁ hx⟩

/-! ## Along the chain -/

/--
What has a certificate in an epoch is in the locks of the next one. The certificate and the
reporters share an honest validator, and that validator's report holds all its votes, even
those it gave after other reports were sent.
-/
theorem closure_preserves_certified {E : Nat → Epoch} {locks : Nat → List Event}
    (hchain : ChainValid E locks) {k : Nat} {e : Event}
    (h : Certified (E k) (locks k) e) : e ∈ locks (k + 1) := by
  obtain ⟨S, hnd, hq, hv⟩ := h
  obtain ⟨x, hxS, hxR, hx⟩ := quorum_intersection_honest hnd (E k).reportersNodup hq
    (E k).reportersQuorum (E k).safe
  obtain ⟨hclosed, hreport⟩ := (hchain k).2 x hxR hx
  refine hreport e ?_
  rw [← report_holds_every_vote _ _ hclosed]
  exact hv x hxS hx

/-- A lock stays in every later epoch. -/
theorem locks_carried {E : Nat → Epoch} {locks : Nat → List Event}
    (hchain : ChainValid E locks) {i j : Nat} (hij : i ≤ j) {e : Event} (he : e ∈ locks i) :
    e ∈ locks j := by
  obtain ⟨d, rfl⟩ := Nat.exists_eq_add_of_le hij
  induction d with
  | zero => exact he
  | succ d ih => exact (hchain (i + d)).1 e (ih (Nat.le_add_right i d))

/-- No two different events with one `(sender, nonce)` have a certificate in any two epochs. -/
theorem no_double_spend_across_epochs {E : Nat → Epoch} {locks : Nat → List Event}
    (hchain : ChainValid E locks) {i j : Nat} {e₁ e₂ : Event}
    (h₁ : Certified (E i) (locks i) e₁) (h₂ : Certified (E j) (locks j) e₂)
    (hs : e₁.sender = e₂.sender) (hn : e₁.nonce = e₂.nonce) : e₁ = e₂ := by
  -- The later certificate has an honest voter, who was bound by the lock of the earlier one.
  have later : ∀ {a b i j}, i < j → Certified (E i) (locks i) a → Certified (E j) (locks j) b →
      a.sender = b.sender → a.nonce = b.nonce → a = b := by
    intro a b i j hij ha hb has han
    have hlocked : a ∈ locks j :=
      locks_carried hchain hij (closure_preserves_certified hchain ha)
    obtain ⟨x, _, hvote⟩ := certified_has_honest_voter hb
    exact lockAllows_spec (votes_respect_locks _ _ _ hvote) hlocked has han
  rcases Nat.lt_trichotomy i j with hij | rfl | hji
  · exact later hij h₁ h₂ hs hn
  · exact certified_same_epoch h₁ h₂ hs hn
  · exact (later hji h₂ h₁ hs.symm hn.symm).symm

end PSystem.Quorum
