import PSystem.QuorumSafety

/-!
# Rounds for one `(sender, nonce)`: agreement and progress

The vote of `Quorum.lean` is round 0. A sender that signs two versions can split it, and then
no version reaches `2f+1` votes: the key would stay open for ever. Here an honest validator,
after a timeout, moves to round `r + 1` and reports what it saw; the leader of the round proposes
a value justified by `2f+1` reports, and the validators vote again.

A key is decided by a fast certificate (`n` votes of round 0) or by a commit certificate
(`2f+1` precommits of one round, each sent on a prepare certificate of `2f+1` votes of that
round). A prepare certificate alone does not decide: with `n = 3f+1` no rule could recover it
from reports (`split_lock_ambiguous_general`).

The proposal of round `r` is the value of the highest prepare certificate among the reports;
with none, the value with `f+1` votes of round 0 among them; with none, any value.

Main results, with `n = 3f+1`, at most `f` faulty validators and unforgeable signatures:

- `decisions_agree`: two honest validators never decide different values, whatever the
  network does: messages lost, delayed, duplicated, reordered, or forged by faulty validators.
- `good_round_decides`: in a round whose leader is honest and in which the messages between
  honest validators arrive, every honest validator decides. This is where the network
  assumption is: partial synchrony makes such rounds happen, it is not proved here.
- `honest_leader_within_n_rounds`: leaders rotate, so any `n` consecutive rounds have one with
  an honest leader.

The model is about one key. Values are any type with decidable equality: in P-System, the
versions of one `(sender, nonce)`.
-/

namespace PSystem.Rounds

open PSystem.Quorum (nodup_length_le_of_subset length_filter_add_filter_not
  quorum_intersection_honest)

/-- A prepare certificate shown in a report: its round, its value and who signed it. -/
structure Best (n : Nat) (V : Type) where
  round : Nat
  value : V
  signers : List (Fin n)

/-- What a validator reports when it enters a round: its vote of round 0 and its highest
prepare certificate. -/
structure Report (n : Nat) (V : Type) where
  vote0 : Option V
  best : Option (Best n V)

/-- What an honest validator can receive. Any value can be delivered, any number of times. -/
inductive Input (n : Nat) (V : Type) where
  /-- A version, signed by its sender: the vote of round 0. -/
  | request (v : V)
  /-- A prepare certificate: `signers` voted `v` in round `r`. -/
  | prepared (r : Nat) (v : V) (signers : List (Fin n))
  /-- The round took too long. -/
  | timeout
  /-- The leader of round `r` proposes `v`, with the reports `J` of round `r`. -/
  | proposal (r : Nat) (v : V) (J : List (Fin n × Report n V))
  /-- A commit certificate: `signers` precommitted `v` in round `r`. -/
  | committed (r : Nat) (v : V) (signers : List (Fin n))
  /-- A fast certificate: `signers` voted `v` in round 0. -/
  | fast (v : V) (signers : List (Fin n))

/-- The state of an honest validator for one key. Lists are latest first. -/
structure RState (n : Nat) (V : Type) where
  round : Nat
  vote0 : Option V
  prevotes : List (Nat × V)
  best : Option (Best n V)
  precommits : List (Nat × V)
  reports : List (Nat × Report n V)
  decided : Option V

def RState.init {n : Nat} {V : Type} : RState n V := ⟨0, none, [], none, [], [], none⟩

/-- At least `k` distinct signers. Signers are `Fin n`, so outsiders cannot appear. -/
def certOk {n : Nat} (signers : List (Fin n)) (k : Nat) : Bool :=
  decide signers.Nodup && decide (k ≤ signers.length)

/-- The best of a list with the highest round; the first one on a tie. -/
def maxBest {n : Nat} {V : Type} : List (Best n V) → Option (Best n V)
  | [] => none
  | b :: bs =>
      match maxBest bs with
      | none => some b
      | some m => if m.round ≤ b.round then some b else some m

def bestsOf {n : Nat} {V : Type} (J : List (Fin n × Report n V)) : List (Best n V) :=
  J.filterMap fun p => p.2.best

def votesOf {n : Nat} {V : Type} (J : List (Fin n × Report n V)) : List V :=
  J.filterMap fun p => p.2.vote0

variable {n : Nat} {V : Type} [DecidableEq V]

/-- The value the reports force, if any. -/
def choose (f : Nat) (J : List (Fin n × Report n V)) : Option V :=
  match maxBest (bestsOf J) with
  | some b => some b.value
  | none => (votesOf J).find? fun v => decide (f + 1 ≤ (votesOf J).count v)

/-- A proposal an honest validator accepts: `2f+1` reports of distinct members, every prepare
certificate in them of an earlier round and with `2f+1` signers, and the value they force if
they force one. -/
def justified (f r : Nat) (v : V) (J : List (Fin n × Report n V)) : Bool :=
  decide (J.map Prod.fst).Nodup && decide (2 * f + 1 ≤ J.length) &&
    (bestsOf J).all (fun b => decide (b.round < r) && certOk b.signers (2 * f + 1)) &&
    match choose f J with
    | some w => decide (w = v)
    | none => true

/-- One transition of an honest validator. `auth` checks the signature of the sender. -/
def step (f : Nat) (auth : V → Bool) (st : RState n V) : Input n V → RState n V
  | .request v =>
      if decide (st.round = 0) && st.vote0.isNone && auth v then
        { st with vote0 := some v, prevotes := (0, v) :: st.prevotes }
      else st
  | .prepared r v S =>
      if certOk S (2 * f + 1) && decide (r ≤ st.round) then
        { st with
          best :=
            match st.best with
            | some b => if b.round < r then some ⟨r, v, S⟩ else some b
            | none => some ⟨r, v, S⟩
          precommits :=
            if decide (r = st.round) && !(st.precommits.any fun p => p.1 == r) then
              (r, v) :: st.precommits
            else st.precommits }
      else st
  | .timeout =>
      { st with
        round := st.round + 1
        reports := (st.round + 1, ⟨st.vote0, st.best⟩) :: st.reports }
  | .proposal r v J =>
      if decide (r = st.round) && decide (1 ≤ r) && !(st.prevotes.any fun p => p.1 == r) &&
          justified f r v J && auth v then
        { st with prevotes := (r, v) :: st.prevotes }
      else st
  | .committed _ v S =>
      if certOk S (2 * f + 1) && st.decided.isNone then { st with decided := some v } else st
  | .fast v S =>
      if certOk S n && st.decided.isNone then { st with decided := some v } else st

/-- An honest validator that processes its inputs in order. -/
def runNode (f : Nat) (auth : V → Bool) (inputs : List (Input n V)) : RState n V :=
  inputs.foldl (step f auth) RState.init


/-! ## Invariants of an honest validator -/

/-- What an honest validator keeps true, for the inputs `seen` it was given. -/
structure Inv (f : Nat) (auth : V → Bool) (seen : Input n V → Prop) (st : RState n V) : Prop where
  prevote_once : ∀ r v w, (r, v) ∈ st.prevotes → (r, w) ∈ st.prevotes → v = w
  prevote_le : ∀ r v, (r, v) ∈ st.prevotes → r ≤ st.round
  precommit_le : ∀ r v, (r, v) ∈ st.precommits → r ≤ st.round
  report_le : ∀ r rep, (r, rep) ∈ st.reports → 1 ≤ r ∧ r ≤ st.round
  round0_no_reports : st.round = 0 → st.reports = []
  vote0_prevote : ∀ v, st.vote0 = some v ↔ (0, v) ∈ st.prevotes
  report_vote0 : ∀ r rep v, (r, rep) ∈ st.reports → rep.vote0 = some v → (0, v) ∈ st.prevotes
  report_vote0' : ∀ v, (0, v) ∈ st.prevotes → ∀ r rep, (r, rep) ∈ st.reports → rep.vote0 = some v
  precommit_best : ∀ r v, (r, v) ∈ st.precommits → ∃ b, st.best = some b ∧ r ≤ b.round
  precommit_report : ∀ r v, (r, v) ∈ st.precommits → ∀ r' rep, (r', rep) ∈ st.reports → r < r' →
    ∃ b, rep.best = some b ∧ r ≤ b.round
  prevote_justified : ∀ r v, (r, v) ∈ st.prevotes → 1 ≤ r →
    ∃ J, seen (.proposal r v J) ∧ justified f r v J = true
  prevote_auth : ∀ r v, (r, v) ∈ st.prevotes → auth v = true
  precommit_prepared : ∀ r v, (r, v) ∈ st.precommits →
    ∃ S, seen (.prepared r v S) ∧ certOk S (2 * f + 1) = true
  best_ok : ∀ b, st.best = some b →
    seen (.prepared b.round b.value b.signers) ∧ certOk b.signers (2 * f + 1) = true ∧ b.round ≤ st.round
  report_best : ∀ r rep b, (r, rep) ∈ st.reports → rep.best = some b →
    seen (.prepared b.round b.value b.signers) ∧ certOk b.signers (2 * f + 1) = true ∧ b.round < r
  decided_cert : ∀ v, st.decided = some v →
    (∃ r S, seen (.committed r v S) ∧ certOk S (2 * f + 1) = true) ∨
      (∃ S, seen (.fast v S) ∧ certOk S n = true)

theorem inv_init (f : Nat) (auth : V → Bool) (seen : Input n V → Prop) :
    Inv f auth seen (RState.init : RState n V) where
  prevote_once := by simp [RState.init]
  prevote_le := by simp [RState.init]
  precommit_le := by simp [RState.init]
  report_le := by simp [RState.init]
  round0_no_reports := by simp [RState.init]
  vote0_prevote := by simp [RState.init]
  report_vote0 := by simp [RState.init]
  report_vote0' := by simp [RState.init]
  precommit_best := by simp [RState.init]
  precommit_report := by simp [RState.init]
  prevote_justified := by simp [RState.init]
  prevote_auth := by simp [RState.init]
  precommit_prepared := by simp [RState.init]
  best_ok := by simp [RState.init]
  report_best := by simp [RState.init]
  decided_cert := by simp [RState.init]

theorem inv_step {f : Nat} {auth : V → Bool} {seen : Input n V → Prop} {st : RState n V}
    (h : Inv f auth seen st) (x : Input n V) (hx : seen x) : Inv f auth seen (step f auth st x) := by
  cases x with
  | request v =>
      simp only [step]
      split
      · rename_i hc
        simp only [Bool.and_eq_true, decide_eq_true_eq, Option.isNone_iff_eq_none] at hc
        obtain ⟨⟨h0, hv⟩, ha⟩ := hc
        have hno : ∀ w, (0, w) ∉ st.prevotes := fun w hw => by
          have := (h.vote0_prevote w).2 hw
          rw [hv] at this
          cases this
        have hrep : st.reports = [] := h.round0_no_reports h0
        exact {
          prevote_once := by
            intro r a b ha' hb'
            simp only [List.mem_cons, Prod.mk.injEq] at ha' hb'
            rcases ha' with ⟨rfl, rfl⟩ | ha' <;> rcases hb' with ⟨hr, rfl⟩ | hb'
            · rfl
            · exact absurd hb' (hno b)
            · subst hr; exact absurd ha' (hno a)
            · exact h.prevote_once r a b ha' hb'
          prevote_le := by
            intro r a ha'
            simp only [List.mem_cons, Prod.mk.injEq] at ha'
            rcases ha' with ⟨rfl, rfl⟩ | ha'
            · simp
            · exact h.prevote_le r a ha'
          precommit_le := h.precommit_le
          report_le := h.report_le
          round0_no_reports := h.round0_no_reports
          vote0_prevote := by
            intro w
            simp only [List.mem_cons, Prod.mk.injEq, true_and, Option.some.injEq]
            constructor
            · intro hw; exact Or.inl hw.symm
            · rintro (hw | hw)
              · exact hw.symm
              · exact absurd hw (hno w)
          report_vote0 := by simp [hrep]
          report_vote0' := by simp [hrep]
          precommit_best := h.precommit_best
          precommit_report := h.precommit_report
          prevote_justified := by
            intro r a ha' hr
            simp only [List.mem_cons, Prod.mk.injEq] at ha'
            rcases ha' with ⟨rfl, rfl⟩ | ha'
            · omega
            · exact h.prevote_justified r a ha' hr
          prevote_auth := by
            intro r a ha'
            simp only [List.mem_cons, Prod.mk.injEq] at ha'
            rcases ha' with ⟨rfl, rfl⟩ | ha'
            · exact ha
            · exact h.prevote_auth r a ha'
          precommit_prepared := h.precommit_prepared
          best_ok := h.best_ok
          report_best := h.report_best
          decided_cert := h.decided_cert }
      · exact h
  | prepared r v S =>
      simp only [step]
      split
      · rename_i hc
        simp only [Bool.and_eq_true, decide_eq_true_eq] at hc
        obtain ⟨hS, hr⟩ := hc
        -- The new best has a round of at least `r` and of at least the old one.
        have hbest : ∀ b', (match st.best with
              | some b => if b.round < r then some ⟨r, v, S⟩ else some b
              | none => some (⟨r, v, S⟩ : Best n V)) = some b' →
            (b' = ⟨r, v, S⟩ ∨ st.best = some b') ∧ r ≤ b'.round ∧
              (∀ b, st.best = some b → b.round ≤ b'.round) := by
          intro b' hb'
          cases hsb : st.best with
          | none =>
              rw [hsb] at hb'
              simp only [Option.some.injEq] at hb'
              subst hb'
              exact ⟨Or.inl rfl, Nat.le_refl _, by simp⟩
          | some b =>
              rw [hsb] at hb'
              simp only at hb'
              split at hb'
              · simp only [Option.some.injEq] at hb'
                subst hb'
                refine ⟨Or.inl rfl, Nat.le_refl _, ?_⟩
                intro c hc
                simp only [Option.some.injEq] at hc
                subst hc
                simp only
                omega
              · simp only [Option.some.injEq] at hb'
                subst hb'
                refine ⟨Or.inr rfl, by omega, ?_⟩
                intro c hc
                simp only [Option.some.injEq] at hc
                subst hc
                exact Nat.le_refl _
        have hsome : ∃ b', (match st.best with
              | some b => if b.round < r then some ⟨r, v, S⟩ else some b
              | none => some (⟨r, v, S⟩ : Best n V)) = some b' := by
          cases st.best with
          | none => exact ⟨_, rfl⟩
          | some b =>
              simp only
              split
              · exact ⟨_, rfl⟩
              · exact ⟨_, rfl⟩
        obtain ⟨b', hb'⟩ := hsome
        obtain ⟨hb'src, hb'r, hb'mono⟩ := hbest b' hb'
        have hpc : ∀ r₁ v₁, (r₁, v₁) ∈ (if decide (r = st.round) &&
              !(st.precommits.any fun p => p.1 == r) then (r, v) :: st.precommits
              else st.precommits) → (r₁ = r ∧ v₁ = v ∧ r = st.round) ∨ (r₁, v₁) ∈ st.precommits := by
          intro r₁ v₁ hm
          split at hm
          · rename_i hcond
            simp only [Bool.and_eq_true, decide_eq_true_eq] at hcond
            simp only [List.mem_cons, Prod.mk.injEq] at hm
            rcases hm with ⟨h1, h2⟩ | hm
            · exact Or.inl ⟨h1, h2, hcond.1⟩
            · exact Or.inr hm
          · exact Or.inr hm
        exact {
          prevote_once := h.prevote_once
          prevote_le := h.prevote_le
          precommit_le := by
            intro r₁ v₁ hm
            rcases hpc r₁ v₁ hm with ⟨rfl, _, hr'⟩ | hm
            · simp only; omega
            · exact h.precommit_le r₁ v₁ hm
          report_le := h.report_le
          round0_no_reports := h.round0_no_reports
          vote0_prevote := h.vote0_prevote
          report_vote0 := h.report_vote0
          report_vote0' := h.report_vote0'
          precommit_best := by
            intro r₁ v₁ hm
            refine ⟨b', hb', ?_⟩
            rcases hpc r₁ v₁ hm with ⟨rfl, _, _⟩ | hm
            · exact hb'r
            · obtain ⟨b, hb, hle⟩ := h.precommit_best r₁ v₁ hm
              exact Nat.le_trans hle (hb'mono b hb)
          precommit_report := by
            intro r₁ v₁ hm r' rep hrep hlt
            rcases hpc r₁ v₁ hm with ⟨rfl, _, hround⟩ | hm
            · have := (h.report_le r' rep hrep).2
              omega
            · exact h.precommit_report r₁ v₁ hm r' rep hrep hlt
          prevote_justified := h.prevote_justified
          prevote_auth := h.prevote_auth
          precommit_prepared := by
            intro r₁ v₁ hm
            rcases hpc r₁ v₁ hm with ⟨rfl, rfl, _⟩ | hm
            · exact ⟨S, hx, hS⟩
            · exact h.precommit_prepared r₁ v₁ hm
          best_ok := by
            intro c hc
            simp only at hc
            rw [hb'] at hc
            simp only [Option.some.injEq] at hc
            subst hc
            rcases hb'src with rfl | hold
            · exact ⟨hx, hS, hr⟩
            · exact h.best_ok _ hold
          report_best := h.report_best
          decided_cert := h.decided_cert }
      · exact h
  | timeout =>
      simp only [step]
      exact {
        prevote_once := h.prevote_once
        prevote_le := fun r v hm => Nat.le_succ_of_le (h.prevote_le r v hm)
        precommit_le := fun r v hm => Nat.le_succ_of_le (h.precommit_le r v hm)
        report_le := by
          intro r rep hm
          simp only [List.mem_cons, Prod.mk.injEq] at hm
          rcases hm with ⟨rfl, rfl⟩ | hm
          · dsimp only; omega
          · have := h.report_le r rep hm
            dsimp only; omega
        round0_no_reports := by intro h0; dsimp only at h0; omega
        vote0_prevote := h.vote0_prevote
        report_vote0 := by
          intro r rep w hm hw
          simp only [List.mem_cons, Prod.mk.injEq] at hm
          rcases hm with ⟨rfl, rfl⟩ | hm
          · exact (h.vote0_prevote w).1 hw
          · exact h.report_vote0 r rep w hm hw
        report_vote0' := by
          intro w hw r rep hm
          simp only [List.mem_cons, Prod.mk.injEq] at hm
          rcases hm with ⟨rfl, rfl⟩ | hm
          · exact (h.vote0_prevote w).2 hw
          · exact h.report_vote0' w hw r rep hm
        precommit_best := h.precommit_best
        precommit_report := by
          intro r v hm r' rep hrep hlt
          simp only [List.mem_cons, Prod.mk.injEq] at hrep
          rcases hrep with ⟨rfl, rfl⟩ | hrep
          · exact h.precommit_best r v hm
          · exact h.precommit_report r v hm r' rep hrep hlt
        prevote_justified := h.prevote_justified
        prevote_auth := h.prevote_auth
        precommit_prepared := h.precommit_prepared
        best_ok := by
          intro b hb
          obtain ⟨h1, h2, h3⟩ := h.best_ok b hb
          exact ⟨h1, h2, Nat.le_succ_of_le h3⟩
        report_best := by
          intro r rep b hm hb
          simp only [List.mem_cons, Prod.mk.injEq] at hm
          rcases hm with ⟨rfl, rfl⟩ | hm
          · obtain ⟨h1, h2, h3⟩ := h.best_ok b hb
            exact ⟨h1, h2, by omega⟩
          · exact h.report_best r rep b hm hb
        decided_cert := h.decided_cert }
  | proposal r v J =>
      simp only [step]
      split
      · rename_i hc
        simp only [Bool.and_eq_true, decide_eq_true_eq, Bool.not_eq_true',
          List.any_eq_false, beq_iff_eq] at hc
        obtain ⟨⟨⟨⟨hr, h1⟩, hfree⟩, hj⟩, ha⟩ := hc
        have hfree' : ∀ w, (r, w) ∉ st.prevotes := fun w hw => hfree _ hw rfl
        exact {
          prevote_once := by
            intro r₁ a b ha' hb'
            simp only [List.mem_cons, Prod.mk.injEq] at ha' hb'
            rcases ha' with ⟨rfl, rfl⟩ | ha' <;> rcases hb' with ⟨hr', rfl⟩ | hb'
            · rfl
            · exact absurd hb' (hfree' b)
            · subst hr'; exact absurd ha' (hfree' a)
            · exact h.prevote_once r₁ a b ha' hb'
          prevote_le := by
            intro r₁ a ha'
            simp only [List.mem_cons, Prod.mk.injEq] at ha'
            rcases ha' with ⟨rfl, rfl⟩ | ha'
            · dsimp only; omega
            · exact h.prevote_le r₁ a ha'
          precommit_le := h.precommit_le
          report_le := h.report_le
          round0_no_reports := h.round0_no_reports
          vote0_prevote := by
            intro w
            rw [h.vote0_prevote w]
            simp only [List.mem_cons, Prod.mk.injEq]
            constructor
            · exact Or.inr
            · rintro (⟨h0, _⟩ | hw)
              · omega
              · exact hw
          report_vote0 := by
            intro r₁ rep w hm hw
            exact List.mem_cons_of_mem _ (h.report_vote0 r₁ rep w hm hw)
          report_vote0' := by
            intro w hw
            simp only [List.mem_cons, Prod.mk.injEq] at hw
            rcases hw with ⟨h0, _⟩ | hw
            · omega
            · exact h.report_vote0' w hw
          precommit_best := h.precommit_best
          precommit_report := h.precommit_report
          prevote_justified := by
            intro r₁ a ha' hr₁
            simp only [List.mem_cons, Prod.mk.injEq] at ha'
            rcases ha' with ⟨rfl, rfl⟩ | ha'
            · exact ⟨J, hx, hj⟩
            · exact h.prevote_justified r₁ a ha' hr₁
          prevote_auth := by
            intro r₁ a ha'
            simp only [List.mem_cons, Prod.mk.injEq] at ha'
            rcases ha' with ⟨rfl, rfl⟩ | ha'
            · exact ha
            · exact h.prevote_auth r₁ a ha'
          precommit_prepared := h.precommit_prepared
          best_ok := h.best_ok
          report_best := h.report_best
          decided_cert := h.decided_cert }
      · exact h
  | committed r v S =>
      simp only [step]
      split
      · rename_i hc
        simp only [Bool.and_eq_true, Option.isNone_iff_eq_none] at hc
        exact { h with
          decided_cert := by
            intro w hw
            simp only [Option.some.injEq] at hw
            subst hw
            exact Or.inl ⟨r, S, hx, hc.1⟩ }
      · exact h
  | fast v S =>
      simp only [step]
      split
      · rename_i hc
        simp only [Bool.and_eq_true, Option.isNone_iff_eq_none] at hc
        exact { h with
          decided_cert := by
            intro w hw
            simp only [Option.some.injEq] at hw
            subst hw
            exact Or.inr ⟨S, hx, hc.1⟩ }
      · exact h

theorem inv_foldl {f : Nat} {auth : V → Bool} {seen : Input n V → Prop} :
    ∀ (l : List (Input n V)) (st : RState n V), Inv f auth seen st → (∀ x, x ∈ l → seen x) →
      Inv f auth seen (l.foldl (step f auth) st)
  | [], _, h, _ => h
  | x :: l, st, h, hl => by
      simp only [List.foldl_cons]
      exact inv_foldl l _ (inv_step h x (hl x (by simp))) fun y hy => hl y (by simp [hy])

theorem inv_runNode (f : Nat) (auth : V → Bool) (inputs : List (Input n V)) :
    Inv f auth (· ∈ inputs) (runNode f auth inputs) :=
  inv_foldl inputs _ (inv_init f auth _) fun _ hx => hx


/-! ## Choosing from reports -/

theorem maxBest_cons_ne_none {n : Nat} {V : Type} (b : Best n V) (bs : List (Best n V)) :
    maxBest (b :: bs) ≠ none := by
  simp only [maxBest]
  cases maxBest bs with
  | none => simp
  | some m => simp only; split <;> simp

theorem maxBest_spec {n : Nat} {V : Type} :
    ∀ (bs : List (Best n V)) (m : Best n V), maxBest bs = some m →
      m ∈ bs ∧ ∀ b, b ∈ bs → b.round ≤ m.round
  | [], m, h => by simp [maxBest] at h
  | b :: bs, m, h => by
      simp only [maxBest] at h
      cases hm : maxBest bs with
      | none =>
          rw [hm] at h
          simp only [Option.some.injEq] at h
          subst h
          have : bs = [] := by
            cases bs with
            | nil => rfl
            | cons c cs => exact absurd hm (maxBest_cons_ne_none c cs)
          subst this
          simp
      | some m' =>
          rw [hm] at h
          obtain ⟨hmem, hmax⟩ := maxBest_spec bs m' hm
          simp only at h
          split at h
          · simp only [Option.some.injEq] at h
            subst h
            refine ⟨by simp, ?_⟩
            intro c hc
            simp only [List.mem_cons] at hc
            rcases hc with rfl | hc
            · exact Nat.le_refl _
            · exact Nat.le_trans (hmax c hc) (by omega)
          · simp only [Option.some.injEq] at h
            subst h
            refine ⟨by simp [hmem], ?_⟩
            intro c hc
            simp only [List.mem_cons] at hc
            rcases hc with rfl | hc
            · omega
            · exact hmax c hc

theorem maxBest_isSome {n : Nat} {V : Type} :
    ∀ (bs : List (Best n V)) (b : Best n V), b ∈ bs → ∃ m, maxBest bs = some m
  | [], _, h => by simp at h
  | c :: bs, _, _ => by
      simp only [maxBest]
      cases maxBest bs with
      | none => exact ⟨c, rfl⟩
      | some m => simp only; split <;> exact ⟨_, rfl⟩

theorem mem_bestsOf {n : Nat} {V : Type} {J : List (Fin n × Report n V)} {b : Best n V} :
    b ∈ bestsOf J ↔ ∃ k rep, (k, rep) ∈ J ∧ rep.best = some b := by
  simp [bestsOf, List.mem_filterMap]

theorem mem_votesOf {n : Nat} {V : Type} {J : List (Fin n × Report n V)} {v : V} :
    v ∈ votesOf J ↔ ∃ k rep, (k, rep) ∈ J ∧ rep.vote0 = some v := by
  simp [votesOf, List.mem_filterMap]

/-- With a prepare certificate among the reports, the proposal is the value of the highest. -/
theorem justified_best {f r : Nat} {v : V} {J : List (Fin n × Report n V)}
    (hj : justified f r v J = true) {b : Best n V} (hb : b ∈ bestsOf J) :
    ∃ m, m ∈ bestsOf J ∧ b.round ≤ m.round ∧ m.round < r ∧ certOk m.signers (2 * f + 1) = true ∧
      m.value = v := by
  obtain ⟨m, hm⟩ := maxBest_isSome _ b hb
  obtain ⟨hmem, hmax⟩ := maxBest_spec _ m hm
  simp only [justified, Bool.and_eq_true, decide_eq_true_eq, List.all_eq_true] at hj
  obtain ⟨⟨⟨_, _⟩, hall⟩, hchoose⟩ := hj
  have hm' := hall m hmem
  simp only [choose, hm, decide_eq_true_eq] at hchoose
  exact ⟨m, hmem, hmax b hb, hm'.1, hm'.2, hchoose⟩

theorem justified_reporters {f r : Nat} {v : V} {J : List (Fin n × Report n V)}
    (hj : justified f r v J = true) :
    (J.map Prod.fst).Nodup ∧ 2 * f + 1 ≤ (J.map Prod.fst).length := by
  simp only [justified, Bool.and_eq_true, decide_eq_true_eq] at hj
  simp only [List.length_map]
  exact ⟨hj.1.1.1, hj.1.1.2⟩

/-! ## A run -/

section Run

variable (f : Nat) (auth : V → Bool) (F : List (Fin n)) (inputs : Fin n → List (Input n V))

/-- The state of validator `i` at the end of the run. -/
def final (i : Fin n) : RState n V := runNode f auth (inputs i)

/-- `2f+1` validators voted `v` in round `r`; the honest ones really did. -/
def Prepared (r : Nat) (v : V) : Prop :=
  ∃ S : List (Fin n), S.Nodup ∧ 2 * f + 1 ≤ S.length ∧
    ∀ j, j ∈ S → j ∉ F → (r, v) ∈ (final f auth inputs j).prevotes

/-- `2f+1` validators precommitted `v` in round `r`; the honest ones really did. -/
def Committed (r : Nat) (v : V) : Prop :=
  ∃ C : List (Fin n), C.Nodup ∧ 2 * f + 1 ≤ C.length ∧
    ∀ j, j ∈ C → j ∉ F → (r, v) ∈ (final f auth inputs j).precommits

/--
Signatures cannot be forged: what a certificate or a report delivered to an honest validator
says of an honest validator, it did. Faulty validators can sign anything.
-/
structure Unforgeable : Prop where
  prepared : ∀ u, u ∉ F → ∀ r v S, Input.prepared r v S ∈ inputs u →
    ∀ j, j ∈ S → j ∉ F → (r, v) ∈ (final f auth inputs j).prevotes
  proposal_best : ∀ u, u ∉ F → ∀ r v J, Input.proposal r v J ∈ inputs u →
    ∀ k rep b, (k, rep) ∈ J → rep.best = some b →
      ∀ j, j ∈ b.signers → j ∉ F → (b.round, b.value) ∈ (final f auth inputs j).prevotes
  proposal_report : ∀ u, u ∉ F → ∀ r v J, Input.proposal r v J ∈ inputs u →
    ∀ j rep, (j, rep) ∈ J → j ∉ F → (r, rep) ∈ (final f auth inputs j).reports
  committed : ∀ u, u ∉ F → ∀ r v S, Input.committed r v S ∈ inputs u →
    ∀ j, j ∈ S → j ∉ F → (r, v) ∈ (final f auth inputs j).precommits
  fast : ∀ u, u ∉ F → ∀ v S, Input.fast v S ∈ inputs u →
    ∀ j, j ∈ S → j ∉ F → (0, v) ∈ (final f auth inputs j).prevotes

end Run

section Safety

variable {f : Nat} {auth : V → Bool} {F : List (Fin n)} {inputs : Fin n → List (Input n V)}

theorem honest_in {S : List (Fin n)} (hn : n = 3 * f + 1) (hF : F.length ≤ f)
    (hS : S.Nodup) (hq : 2 * f + 1 ≤ S.length) : ∃ j, j ∈ S ∧ j ∉ F := by
  obtain ⟨j, hj, _, hjF⟩ := quorum_intersection_honest (F := F) hS hS hq hq (by omega)
  exact ⟨j, hj, hjF⟩

theorem inv_final (i : Fin n) :
    Inv f auth (· ∈ inputs i) (final f auth inputs i) := inv_runNode f auth (inputs i)

theorem certOk_spec {S : List (Fin n)} {k : Nat} (h : certOk S k = true) : S.Nodup ∧ k ≤ S.length := by
  simpa [certOk] using h

theorem prepared_same_round (hn : n = 3 * f + 1) (hF : F.length ≤ f) {r : Nat} {v w : V}
    (hv : Prepared f auth F inputs r v) (hw : Prepared f auth F inputs r w) : v = w := by
  obtain ⟨A, hA, hAq, hAv⟩ := hv
  obtain ⟨B, hB, hBq, hBw⟩ := hw
  obtain ⟨j, hjA, hjB, hjF⟩ := quorum_intersection_honest (F := F) hA hB hAq hBq (by omega)
  exact (inv_final (f := f) (auth := auth) (inputs := inputs) j).prevote_once r v w
    (hAv j hjA hjF) (hBw j hjB hjF)

/-- A certificate an honest validator accepted, or that a report it accepted shows, is prepared. -/
theorem prepared_of_input (hU : Unforgeable f auth F inputs) {u : Fin n} (hu : u ∉ F)
    {r : Nat} {v : V} {S : List (Fin n)} (hin : Input.prepared r v S ∈ inputs u)
    (hS : certOk S (2 * f + 1) = true) : Prepared f auth F inputs r v :=
  ⟨S, (certOk_spec hS).1, (certOk_spec hS).2, hU.prepared u hu r v S hin⟩

/-- An honest precommit is on a prepared value. -/
theorem prepared_of_precommit (hU : Unforgeable f auth F inputs) {j : Fin n} (hj : j ∉ F)
    {r : Nat} {v : V} (h : (r, v) ∈ (final f auth inputs j).precommits) :
    Prepared f auth F inputs r v := by
  obtain ⟨S, hin, hS⟩ := (inv_final (inputs := inputs) j).precommit_prepared r v h
  exact prepared_of_input hU hj hin hS

theorem prepared_of_committed (hn : n = 3 * f + 1) (hF : F.length ≤ f)
    (hU : Unforgeable f auth F inputs) {r : Nat} {v : V} (h : Committed f auth F inputs r v) :
    Prepared f auth F inputs r v := by
  obtain ⟨C, hC, hCq, hCv⟩ := h
  obtain ⟨j, hjC, hjF⟩ := honest_in hn hF hC hCq
  exact prepared_of_precommit hU hjF (hCv j hjC hjF)

/-- An honest vote in round `r ≥ 1` comes with its reports, and they show a best of round at
least `r₀` once a value is committed in round `r₀ < r`. -/
theorem committed_shows_in_reports (hn : n = 3 * f + 1) (hF : F.length ≤ f)
    (hU : Unforgeable f auth F inputs) {r₀ r : Nat} {v w : V} (hc : Committed f auth F inputs r₀ v)
    (hlt : r₀ < r) {j : Fin n} (hj : j ∉ F) (hw : (r, w) ∈ (final f auth inputs j).prevotes) :
    ∃ J, Input.proposal r w J ∈ inputs j ∧ justified f r w J = true ∧
      ∃ b, b ∈ bestsOf J ∧ r₀ ≤ b.round := by
  obtain ⟨J, hin, hjust⟩ := (inv_final (inputs := inputs) j).prevote_justified r w hw (by omega)
  obtain ⟨hD, hDq⟩ := justified_reporters hjust
  obtain ⟨C, hC, hCq, hCv⟩ := hc
  obtain ⟨k, hkC, hkD, hkF⟩ := quorum_intersection_honest (F := F) hC hD hCq hDq (by omega)
  obtain ⟨⟨k', rep⟩, hkJ, hk'⟩ := List.mem_map.mp hkD
  simp only at hk'
  subst hk'
  have hrep := hU.proposal_report j hj r w J hin k' rep hkJ hkF
  obtain ⟨b, hb, hbr⟩ := (inv_final (inputs := inputs) k').precommit_report r₀ v
    (hCv k' hkC hkF) r rep hrep hlt
  exact ⟨J, hin, hjust, b, mem_bestsOf.mpr ⟨k', rep, hkJ, hb⟩, hbr⟩

/-- The highest prepare certificate of a justified proposal is prepared. -/
theorem best_prepared (hU : Unforgeable f auth F inputs) {j : Fin n} (hj : j ∉ F) {r : Nat}
    {w : V} {J : List (Fin n × Report n V)} (hin : Input.proposal r w J ∈ inputs j)
    {m : Best n V} (hm : m ∈ bestsOf J) (hS : certOk m.signers (2 * f + 1) = true) :
    Prepared f auth F inputs m.round m.value := by
  obtain ⟨k, rep, hkJ, hrep⟩ := mem_bestsOf.mp hm
  exact ⟨m.signers, (certOk_spec hS).1, (certOk_spec hS).2,
    hU.proposal_best j hj r w J hin k rep m hkJ hrep⟩

/--
The core of agreement. Once `v` is committed in round `r₀`, no other value is prepared in any
later round: the reports that justify a later proposal include one of an honest validator that
precommitted `v`, so they show a prepare certificate of round `r₀` or more, and by induction it
is for `v`.
-/
theorem committed_locks (hn : n = 3 * f + 1) (hF : F.length ≤ f) (hU : Unforgeable f auth F inputs)
    {r₀ : Nat} {v : V} (hc : Committed f auth F inputs r₀ v) :
    ∀ r, r₀ ≤ r → ∀ w, Prepared f auth F inputs r w → w = v := by
  intro r
  induction r using Nat.strongRecOn with
  | _ r ih =>
      intro hle w hw
      rcases Nat.eq_or_lt_of_le hle with rfl | hlt
      · exact prepared_same_round hn hF hw (prepared_of_committed hn hF hU hc)
      · obtain ⟨S, hS, hSq, hSw⟩ := hw
        obtain ⟨j, hjS, hjF⟩ := honest_in hn hF hS hSq
        obtain ⟨J, hin, hjust, b, hb, hbr⟩ :=
          committed_shows_in_reports hn hF hU hc hlt hjF (hSw j hjS hjF)
        obtain ⟨m, hm, hbm, hmr, hmS, hmw⟩ := justified_best hjust hb
        have := ih m.round hmr (Nat.le_trans hbr hbm) m.value (best_prepared hU hjF hin hm hmS)
        rw [← hmw, this]

/-! ## The fast path -/

theorem count_filterMap {α β : Type} [DecidableEq β] (g : α → Option β) (b : β) :
    ∀ l : List α, (l.filterMap g).count b = (l.filter fun a => g a == some b).length
  | [] => rfl
  | a :: l => by
      simp only [List.filterMap_cons, List.filter_cons]
      cases hg : g a with
      | none => simp [count_filterMap g b l]
      | some c =>
          by_cases hcb : c = b
          · subst hcb; simp [count_filterMap g c l]
          · simp [hcb, count_filterMap g b l]

/-- Entries of reporters in `F`, distinct, are at most `|F|`. -/
theorem faulty_entries {α : Type} {J : List (Fin n × α)} (hD : (J.map Prod.fst).Nodup)
    (P : Fin n × α → Bool) (hP : ∀ p, p ∈ J → P p = true → p.1 ∈ F) :
    (J.filter P).length ≤ F.length := by
  have hnd : ((J.filter P).map Prod.fst).Nodup :=
    List.Nodup.sublist (List.Sublist.map _ List.filter_sublist) hD
  have := nodup_length_le_of_subset hnd fun x hx => by
    obtain ⟨p, hp, rfl⟩ := List.mem_map.mp hx
    obtain ⟨hpJ, hpP⟩ := List.mem_filter.mp hp
    exact hP p hpJ hpP
  simpa using this

omit [DecidableEq V] in
theorem find_unique {l : List V} {p : V → Bool} {v : V} (hv : v ∈ l) (hpv : p v = true)
    (honly : ∀ u, u ∈ l → p u = true → u = v) : l.find? p = some v := by
  cases h : l.find? p with
  | none =>
      have := List.find?_eq_none.mp h v hv
      simp [hpv] at this
  | some u =>
      have hu := List.mem_of_find?_eq_some h
      have hpu := List.find?_some h
      rw [honly u hu hpu]

theorem filter_length_le_of_imp {α : Type} (p q : α → Bool) :
    ∀ l : List α, (∀ a, a ∈ l → p a = true → q a = true) → (l.filter p).length ≤ (l.filter q).length
  | [], _ => by simp
  | a :: l, h => by
      have ih := filter_length_le_of_imp p q l fun b hb => h b (by simp [hb])
      simp only [List.filter_cons]
      cases hp : p a <;> cases hq : q a
      · simpa using ih
      · simp only [Bool.false_eq_true, ↓reduceIte, List.length_cons]; omega
      · simp [h a (by simp) hp] at hq
      · simpa using ih

/-- When every honest validator voted `v` in round 0, no other value is ever prepared. -/
theorem fast_locks (hn : n = 3 * f + 1) (hF : F.length ≤ f) (hU : Unforgeable f auth F inputs)
    {v : V} (hall : ∀ j, j ∉ F → (0, v) ∈ (final f auth inputs j).prevotes) :
    ∀ r w, Prepared f auth F inputs r w → w = v := by
  intro r
  induction r using Nat.strongRecOn with
  | _ r ih =>
      intro w hw
      obtain ⟨S, hS, hSq, hSw⟩ := hw
      obtain ⟨j, hjS, hjF⟩ := honest_in hn hF hS hSq
      have hjw := hSw j hjS hjF
      rcases Nat.eq_zero_or_pos r with rfl | hr
      · exact (inv_final (inputs := inputs) j).prevote_once 0 w v hjw (hall j hjF)
      · obtain ⟨J, hin, hjust⟩ := (inv_final (inputs := inputs) j).prevote_justified r w hjw hr
        cases hmb : maxBest (bestsOf J) with
        | some m =>
            obtain ⟨hm, _⟩ := maxBest_spec _ m hmb
            obtain ⟨m', hm', _, hm'r, hm'S, hm'w⟩ := justified_best hjust hm
            rw [← hm'w]
            exact ih m'.round hm'r m'.value (best_prepared hU hjF hin hm' hm'S)
        | none =>
            -- No prepare certificate: the votes of round 0 decide, and the honest ones are for `v`.
            obtain ⟨hD, hDq⟩ := justified_reporters hjust
            have hrep : ∀ k rep, (k, rep) ∈ J → k ∉ F → rep.vote0 = some v := by
              intro k rep hk hkF
              exact (inv_final (inputs := inputs) k).report_vote0' v (hall k hkF) r rep
                (hU.proposal_report j hjF r w J hin k rep hk hkF)
            have hother : ∀ u, u ≠ v → (votesOf J).count u ≤ F.length := by
              intro u hu
              rw [votesOf, count_filterMap]
              refine faulty_entries hD _ fun p hp hpu => ?_
              refine Classical.byContradiction fun hpF => ?_
              have := hrep p.1 p.2 hp hpF
              simp only [beq_iff_eq] at hpu
              rw [this] at hpu
              exact hu (Option.some.inj hpu).symm
            have hmine : F.length + (f + 1) ≤ F.length + (votesOf J).count v := by
              rw [votesOf, count_filterMap]
              have hsplit := length_filter_add_filter_not (fun p : Fin n × Report n V => decide (p.1 ∈ F)) J
              have hbad := faulty_entries hD (fun p : Fin n × Report n V => decide (p.1 ∈ F))
                fun p _ hp => by simpa using hp
              have hsub : (J.filter fun p => !decide (p.1 ∈ F)).length ≤
                  (J.filter fun p => p.2.vote0 == some v).length := by
                refine filter_length_le_of_imp _ _ J fun p hp hpF => ?_
                simp only [Bool.not_eq_true', decide_eq_false_iff_not] at hpF
                simp [hrep p.1 p.2 hp hpF]
              simp only [List.length_map] at hDq
              omega
            have hchoose : choose f J = some v := by
              simp only [choose, hmb]
              refine find_unique ?_ (by simp only [decide_eq_true_eq]; omega) ?_
              · exact List.count_pos_iff.mp (by omega)
              · intro u _ hu
                simp only [decide_eq_true_eq] at hu
                refine Classical.byContradiction fun huv => ?_
                have := hother u huv
                omega
            simp only [justified, Bool.and_eq_true, hchoose, decide_eq_true_eq] at hjust
            exact hjust.2.symm
          
/-- `n` distinct members are all of them. -/
theorem mem_of_all {S : List (Fin n)} (hS : S.Nodup) (hlen : n ≤ S.length) (j : Fin n) : j ∈ S := by
  refine Classical.byContradiction fun hj => ?_
  have hle := nodup_length_le_of_subset hS fun x hx =>
    (List.mem_erase_of_ne fun (h : x = j) => hj (h ▸ hx)).2 (List.mem_finRange x)
  rw [List.length_erase_of_mem (List.mem_finRange j), List.length_finRange] at hle
  have : 0 < n := Fin.pos j
  omega

/-- What an honest decision rests on: a commit certificate, or the votes of every honest
validator in round 0. -/
theorem decision_grounds (hU : Unforgeable f auth F inputs) {u : Fin n} (hu : u ∉ F) {v : V}
    (hd : (final f auth inputs u).decided = some v) :
    (∃ r, Committed f auth F inputs r v) ∨ (∀ j, j ∉ F → (0, v) ∈ (final f auth inputs j).prevotes) := by
  rcases (inv_final (inputs := inputs) u).decided_cert v hd with ⟨r, S, hin, hS⟩ | ⟨S, hin, hS⟩
  · exact Or.inl ⟨r, S, (certOk_spec hS).1, (certOk_spec hS).2, hU.committed u hu r v S hin⟩
  · exact Or.inr fun j hj =>
      hU.fast u hu v S hin j (mem_of_all (certOk_spec hS).1 (certOk_spec hS).2 j) hj

/--
**Agreement.** Two honest validators never decide different values for one key, with
`n = 3f+1`, at most `f` faulty validators and unforgeable signatures. Nothing is assumed about
the network: each validator can be given any inputs, in any order.
-/
theorem decisions_agree (hn : n = 3 * f + 1) (hF : F.length ≤ f) (hU : Unforgeable f auth F inputs)
    {u u' : Fin n} (hu : u ∉ F) (hu' : u' ∉ F) {v w : V}
    (hv : (final f auth inputs u).decided = some v) (hw : (final f auth inputs u').decided = some w) :
    v = w := by
  rcases decision_grounds hU hu hv with ⟨r, hcv⟩ | hfv <;>
    rcases decision_grounds hU hu' hw with ⟨r', hcw⟩ | hfw
  · rcases Nat.le_total r r' with hle | hle
    · exact (committed_locks hn hF hU hcv r' hle w (prepared_of_committed hn hF hU hcw)).symm
    · exact committed_locks hn hF hU hcw r hle v (prepared_of_committed hn hF hU hcv)
  · exact fast_locks hn hF hU hfw r v (prepared_of_committed hn hF hU hcv)
  · exact (fast_locks hn hF hU hfv r' w (prepared_of_committed hn hF hU hcw)).symm
  · obtain ⟨j, _, hj⟩ := honest_in (S := List.finRange n) hn hF (List.nodup_finRange n)
      (by simp [hn]; omega)
    exact (inv_final (inputs := inputs) j).prevote_once 0 v w (hfv j hj) (hfw j hj)

/-- What a decision certificate shows: a commit certificate, or every honest vote of round 0. -/
def Grounds (f : Nat) (auth : V → Bool) (F : List (Fin n)) (inputs : Fin n → List (Input n V))
    (v : V) : Prop :=
  (∃ r, Committed f auth F inputs r v) ∨ (∀ j, j ∉ F → (0, v) ∈ (final f auth inputs j).prevotes)

/-- Two decision certificates for one key are for one value, wherever they are shown. -/
theorem grounds_agree (hn : n = 3 * f + 1) (hF : F.length ≤ f) (hU : Unforgeable f auth F inputs)
    {v w : V} (hv : Grounds f auth F inputs v) (hw : Grounds f auth F inputs w) : v = w := by
  rcases hv with ⟨r, hcv⟩ | hfv <;> rcases hw with ⟨r', hcw⟩ | hfw
  · rcases Nat.le_total r r' with hle | hle
    · exact (committed_locks hn hF hU hcv r' hle w (prepared_of_committed hn hF hU hcw)).symm
    · exact committed_locks hn hF hU hcw r hle v (prepared_of_committed hn hF hU hcv)
  · exact fast_locks hn hF hU hfw r v (prepared_of_committed hn hF hU hcv)
  · exact (fast_locks hn hF hU hfv r' w (prepared_of_committed hn hF hU hcw)).symm
  · obtain ⟨j, _, hj⟩ := honest_in (S := List.finRange n) hn hF (List.nodup_finRange n)
      (by simp [hn]; omega)
    exact (inv_final (inputs := inputs) j).prevote_once 0 v w (hfv j hj) (hfw j hj)

/-- A commit certificate an honest validator accepted, or a fast one, shows its grounds. -/
theorem grounds_of_committed_input (hU : Unforgeable f auth F inputs) {u : Fin n} (hu : u ∉ F)
    {r : Nat} {v : V} {S : List (Fin n)} (hin : Input.committed r v S ∈ inputs u)
    (hS : certOk S (2 * f + 1) = true) : Grounds f auth F inputs v :=
  Or.inl ⟨r, S, (certOk_spec hS).1, (certOk_spec hS).2, hU.committed u hu r v S hin⟩

/-! ## Closing an epoch

An honest member reports for the closure of its epoch only once it has decided every key it
voted on, with the decision certificate. Then the closure holds every value decided in the
epoch, whichever quorum reported, and only those values. -/

/--
**Every decided value is in every closure.** `R` are the reporters of a closure: `2f+1` distinct
members, and the honest ones among them had decided each key they voted on. If an honest
validator decided `v`, an honest reporter decided `v` too, so the closure holds it.
-/
theorem decided_in_closure (hn : n = 3 * f + 1) (hF : F.length ≤ f) (hU : Unforgeable f auth F inputs)
    {R : List (Fin n)} (hR : R.Nodup) (hRq : 2 * f + 1 ≤ R.length)
    (hwait : ∀ k, k ∈ R → k ∉ F →
      ((final f auth inputs k).prevotes ≠ [] ∨ (final f auth inputs k).precommits ≠ []) →
        (final f auth inputs k).decided.isSome)
    {u : Fin n} (hu : u ∉ F) {v : V} (hv : (final f auth inputs u).decided = some v) :
    ∃ k, k ∈ R ∧ k ∉ F ∧ (final f auth inputs k).decided = some v := by
  -- A reporter that took part in the decision of `v`.
  have hpart : ∃ k, k ∈ R ∧ k ∉ F ∧
      ((final f auth inputs k).prevotes ≠ [] ∨ (final f auth inputs k).precommits ≠ []) := by
    rcases decision_grounds hU hu hv with ⟨r, C, hC, hCq, hCv⟩ | hfv
    · obtain ⟨k, hkC, hkR, hkF⟩ := quorum_intersection_honest (F := F) hC hR hCq hRq (by omega)
      exact ⟨k, hkR, hkF, Or.inr (List.ne_nil_of_mem (hCv k hkC hkF))⟩
    · obtain ⟨k, hkR, hkF⟩ := honest_in hn hF hR hRq
      exact ⟨k, hkR, hkF, Or.inl (List.ne_nil_of_mem (hfv k hkF))⟩
  obtain ⟨k, hkR, hkF, hk⟩ := hpart
  obtain ⟨x, hx⟩ := Option.isSome_iff_exists.mp (hwait k hkR hkF hk)
  exact ⟨k, hkR, hkF, by rw [hx, decisions_agree hn hF hU hkF hu hx hv]⟩

/--
**A decided value is in every closure that lists what its reporters voted for in any round.**
No waiting is needed: whichever `2f+1` members report, one of them is honest and precommitted the
value, or voted it in round 0 when the decision was fast.
-/
theorem voted_in_closure (hn : n = 3 * f + 1) (hF : F.length ≤ f) (hU : Unforgeable f auth F inputs)
    {R : List (Fin n)} (hR : R.Nodup) (hRq : 2 * f + 1 ≤ R.length)
    {u : Fin n} (hu : u ∉ F) {v : V} (hv : (final f auth inputs u).decided = some v) :
    ∃ k, k ∈ R ∧ k ∉ F ∧
      ((∃ r, (r, v) ∈ (final f auth inputs k).precommits) ∨ (0, v) ∈ (final f auth inputs k).prevotes) := by
  rcases decision_grounds hU hu hv with ⟨r, C, hC, hCq, hCv⟩ | hfv
  · obtain ⟨k, hkC, hkR, hkF⟩ := quorum_intersection_honest (F := F) hC hR hCq hRq (by omega)
    exact ⟨k, hkR, hkF, Or.inl ⟨r, hCv k hkC hkF⟩⟩
  · obtain ⟨k, hkR, hkF⟩ := honest_in hn hF hR hRq
    exact ⟨k, hkR, hkF, Or.inr (hfv k hkF)⟩

end Safety

/-! ## The next epoch

The members of the next committee take the decisions of the closure as locks: for a locked key
they vote only for its value, in any round. Their check of a value is `auth` and the lock. -/

section NextEpoch

variable {f : Nat} {auth : V → Bool} {F : List (Fin n)} {inputs : Fin n → List (Input n V)}

/-- With every honest member locked on `v`, every value decided is `v`. -/
theorem locked_epoch_decides_the_lock (hn : n = 3 * f + 1) (hF : F.length ≤ f)
    (hU : Unforgeable f auth F inputs) {v : V} (hlock : ∀ w, auth w = true → w = v)
    {u : Fin n} (hu : u ∉ F) {w : V} (hw : (final f auth inputs u).decided = some w) : w = v := by
  have hprep : ∀ r x, Prepared f auth F inputs r x → x = v := by
    intro r x hx
    obtain ⟨S, hS, hSq, hSx⟩ := hx
    obtain ⟨j, hjS, hjF⟩ := honest_in hn hF hS hSq
    exact hlock x ((inv_final (inputs := inputs) j).prevote_auth r x (hSx j hjS hjF))
  rcases decision_grounds hU hu hw with ⟨r, hc⟩ | hfw
  · exact hprep r w (prepared_of_committed hn hF hU hc)
  · obtain ⟨j, _, hj⟩ := honest_in (S := List.finRange n) hn hF (List.nodup_finRange n)
      (by simp [hn]; omega)
    exact hlock w ((inv_final (inputs := inputs) j).prevote_auth 0 w (hfw j hj))

/--
**No double spend across two epochs.** An honest validator of epoch `i` decided `v`. The
closure of epoch `i` holds, for this key, a decision certificate for some `x` (by
`decided_in_closure` it holds one, from an honest reporter), and the members of epoch `i+1`
vote only for `x`. Then whatever an honest validator of epoch `i+1` decides is `v`.
-/
theorem no_double_spend_next_epoch (hn : n = 3 * f + 1) (hF : F.length ≤ f)
    {auth₁ : V → Bool} {inputs₁ : Fin n → List (Input n V)} (hU₁ : Unforgeable f auth₁ F inputs₁)
    {F₂ : List (Fin n)} (hF₂ : F₂.length ≤ f)
    {auth₂ : V → Bool} {inputs₂ : Fin n → List (Input n V)} (hU₂ : Unforgeable f auth₂ F₂ inputs₂)
    {u : Fin n} (hu : u ∉ F) {v : V} (hv : (final f auth₁ inputs₁ u).decided = some v)
    {x : V} (hx : Grounds f auth₁ F inputs₁ x) (hlock : ∀ w, auth₂ w = true → w = x)
    {u₂ : Fin n} (hu₂ : u₂ ∉ F₂) {w : V} (hw : (final f auth₂ inputs₂ u₂).decided = some w) :
    w = v := by
  have hxv : x = v := grounds_agree hn hF hU₁ hx
    (decision_grounds hU₁ hu hv)
  rw [locked_epoch_decides_the_lock hn hF₂ hU₂ hlock hu₂ hw, hxv]

end NextEpoch

/-! ## Progress -/

section Liveness

variable {f : Nat} {auth : V → Bool} {F : List (Fin n)}

/-- What a validator in state `st` reports when it enters a round. -/
def reportOf (st : RState n V) : Report n V := ⟨st.vote0, st.best⟩

/-- The honest validators. -/
def honest (F : List (Fin n)) : List (Fin n) := (List.finRange n).filter fun i => decide (i ∉ F)

/-- The reports of every honest validator, as the leader of a good round receives them. -/
def goodReports (F : List (Fin n)) (st : Fin n → RState n V) : List (Fin n × Report n V) :=
  (honest F).map fun i => (i, reportOf (st i))

/-- What an honest leader proposes from them; `e0` is a version it knows. -/
def goodProposal (f : Nat) (F : List (Fin n)) (st : Fin n → RState n V) (e0 : V) : V :=
  (choose f (goodReports F st)).getD e0

/--
A good round `r` for validator `i`, as it receives it: the timeouts up to round `r`, the
proposal of an honest leader with the reports of every honest validator, then the prepare and
commit certificates made of the votes of every honest validator. Partial synchrony is the
assumption that such a round comes: a leader that is honest and messages between honest
validators that arrive before the timeout.
-/
def goodRound (f : Nat) (F : List (Fin n)) (st : Fin n → RState n V) (e0 : V) (r : Nat) (i : Fin n) :
    List (Input n V) :=
  List.replicate (r - (st i).round) .timeout ++
    [.proposal r (goodProposal f F st e0) (goodReports F st),
      .prepared r (goodProposal f F st e0) (honest F),
      .committed r (goodProposal f F st e0) (honest F)]

theorem foldl_timeouts (st : RState n V) :
    ∀ k, (List.replicate k (Input.timeout : Input n V)).foldl (step f auth) st =
      { st with
        round := st.round + k
        reports := ((List.replicate k (Input.timeout : Input n V)).foldl (step f auth) st).reports }
  | 0 => by simp
  | k + 1 => by
      rw [List.replicate_succ', List.foldl_append, foldl_timeouts st k]
      simp only [List.foldl_cons, List.foldl_nil, step]
      simp only [Nat.add_assoc]

theorem honest_nodup : (honest F).Nodup := List.Nodup.sublist List.filter_sublist (List.nodup_finRange n)

theorem honest_length (hn : n = 3 * f + 1) (hF : F.length ≤ f) : 2 * f + 1 ≤ (honest F).length := by
  have hsplit := length_filter_add_filter_not (fun i : Fin n => decide (i ∈ F)) (List.finRange n)
  have hbad : ((List.finRange n).filter fun i => decide (i ∈ F)).length ≤ F.length :=
    nodup_length_le_of_subset (List.Nodup.sublist List.filter_sublist (List.nodup_finRange n))
      fun x hx => by simpa using (List.mem_filter.mp hx).2
  have : (honest F).length = ((List.finRange n).filter fun i => !decide (i ∈ F)).length := by
    simp [honest]
  rw [List.length_finRange] at hsplit
  omega

omit [DecidableEq V] in
theorem mem_goodReports {st : Fin n → RState n V} {k : Fin n} {rep : Report n V}
    (h : (k, rep) ∈ goodReports F st) : k ∉ F ∧ rep = reportOf (st k) := by
  obtain ⟨i, hi, hik⟩ := List.mem_map.mp h
  simp only [Prod.mk.injEq] at hik
  obtain ⟨rfl, rfl⟩ := hik
  exact ⟨by simpa [honest] using hi, rfl⟩

section

variable {pre : Fin n → List (Input n V)}

/-- The proposal of an honest leader passes the check of `auth`. -/
theorem goodProposal_auth (hn : n = 3 * f + 1) (hF : F.length ≤ f) (hU : Unforgeable f auth F pre)
    {e0 : V} (he0 : auth e0 = true) :
    auth (goodProposal f F (final f auth pre) e0) = true := by
  unfold goodProposal choose
  cases hmb : maxBest (bestsOf (goodReports F (final f auth pre))) with
  | some m =>
      obtain ⟨hm, _⟩ := maxBest_spec _ m hmb
      obtain ⟨k, rep, hk, hrep⟩ := mem_bestsOf.mp hm
      obtain ⟨hkF, rfl⟩ := mem_goodReports hk
      obtain ⟨hin, hS, _⟩ := (inv_final (inputs := pre) k).best_ok m hrep
      obtain ⟨j, hjS, hjF⟩ := honest_in hn hF (certOk_spec hS).1 (certOk_spec hS).2
      exact (inv_final (inputs := pre) j).prevote_auth _ _ (hU.prepared k hkF _ _ _ hin j hjS hjF)
  | none =>
      simp only
      cases hfind : (votesOf (goodReports F (final f auth pre))).find?
          (fun v => decide (f + 1 ≤ (votesOf (goodReports F (final f auth pre))).count v)) with
      | none => simpa using he0
      | some w =>
          obtain ⟨k, rep, hk, hw⟩ := mem_votesOf.mp (List.mem_of_find?_eq_some hfind)
          obtain ⟨_, rfl⟩ := mem_goodReports hk
          have := ((inv_final (inputs := pre) k).vote0_prevote w).1 hw
          simpa using (inv_final (inputs := pre) k).prevote_auth 0 w this

/-- The proposal of an honest leader is justified, for every round after the honest ones. -/
theorem goodProposal_justified (hn : n = 3 * f + 1) (hF : F.length ≤ f) {r : Nat}
    (hr : ∀ i, i ∉ F → (final f auth pre i).round < r) (e0 : V) :
    justified f r (goodProposal f F (final f auth pre) e0) (goodReports F (final f auth pre)) = true := by
  simp only [justified, Bool.and_eq_true, decide_eq_true_eq, List.all_eq_true]
  refine ⟨⟨⟨?_, ?_⟩, ?_⟩, ?_⟩
  · have : ((goodReports F (final f auth pre)).map Prod.fst) = honest F := by
      simp [goodReports, List.map_map, Function.comp_def]
    rw [this]
    exact honest_nodup
  · simp only [goodReports, List.length_map]
    exact honest_length hn hF
  · intro b hb
    obtain ⟨k, rep, hk, hrep⟩ := mem_bestsOf.mp hb
    obtain ⟨hkF, rfl⟩ := mem_goodReports hk
    obtain ⟨_, hS, hle⟩ := (inv_final (inputs := pre) k).best_ok b hrep
    exact ⟨Nat.lt_of_le_of_lt hle (hr k hkF), hS⟩
  · unfold goodProposal
    cases choose f (goodReports F (final f auth pre)) with
    | none => rfl
    | some w => simp

/--
**Progress.** In a good round `r` after the rounds the honest validators are in, every honest
validator votes the proposal, precommits it and decides. What happened before is arbitrary.
-/
theorem good_round_decides (hn : n = 3 * f + 1) (hF : F.length ≤ f) (hU : Unforgeable f auth F pre)
    {r : Nat} (hr : ∀ i, i ∉ F → (final f auth pre i).round < r) {e0 : V} (he0 : auth e0 = true)
    {i : Fin n} (hi : i ∉ F) :
    let st := runNode f auth (pre i ++ goodRound f F (final f auth pre) e0 r i)
    let p := goodProposal f F (final f auth pre) e0
    (r, p) ∈ st.prevotes ∧ (r, p) ∈ st.precommits ∧ st.decided.isSome := by
  intro st p
  have hinv := inv_final (f := f) (auth := auth) (inputs := pre) i
  have hri := hr i hi
  have hjust : justified f r p (goodReports F (final f auth pre)) = true :=
    goodProposal_justified (auth := auth) hn hF hr e0
  have hauth : auth p = true := goodProposal_auth hn hF hU he0
  have hH : certOk (honest F) (2 * f + 1) = true := by
    simp [certOk, honest_nodup, honest_length hn hF]
  -- After the timeouts the validator is in round `r`, with no vote and no precommit in it.
  let s₁ := (List.replicate (r - (final f auth pre i).round) (Input.timeout : Input n V)).foldl
    (step f auth) (final f auth pre i)
  have hs₁ : s₁ = { final f auth pre i with
      round := r
      reports := s₁.reports } := by
    have := foldl_timeouts (f := f) (auth := auth) (final f auth pre i) (r - (final f auth pre i).round)
    rw [Nat.add_sub_cancel' (Nat.le_of_lt hri)] at this
    exact this
  have hfree : (s₁.prevotes.any fun q => q.1 == r) = false := by
    rw [hs₁]
    simp only [List.any_eq_false, beq_iff_eq]
    intro q hq hqr
    have := hinv.prevote_le q.1 q.2 hq
    omega
  have hfree' : (s₁.precommits.any fun q => q.1 == r) = false := by
    rw [hs₁]
    simp only [List.any_eq_false, beq_iff_eq]
    intro q hq hqr
    have := hinv.precommit_le q.1 q.2 hq
    omega
  have hround : s₁.round = r := by rw [hs₁]
  have hr1 : 1 ≤ r := by omega
  -- The proposal, then the prepare certificate, then the commit certificate.
  let s₂ := step f auth s₁ (.proposal r p (goodReports F (final f auth pre)))
  have hs₂ : s₂ = { s₁ with prevotes := (r, p) :: s₁.prevotes } := by
    simp only [s₂, step, hround, hfree, hjust, hauth, hr1, decide_true, Bool.not_false,
      Bool.and_self, ↓reduceIte]
  let s₃ := step f auth s₂ (.prepared r p (honest F))
  have hs₃ : (r, p) ∈ s₃.precommits ∧ s₃.prevotes = s₂.prevotes ∧ s₃.decided = s₂.decided := by
    have h2r : s₂.round = r := by rw [hs₂]; exact hround
    have h2pc : (s₂.precommits.any fun q => q.1 == r) = false := by rw [hs₂]; exact hfree'
    simp only [s₃, step, hH, h2r, Nat.le_refl, decide_true, ↓reduceIte, h2pc,
      Bool.not_false, Bool.and_self]
    simp
  have hst : st = step f auth s₃ (.committed r p (honest F)) := by
    simp only [st, runNode, List.foldl_append, goodRound, List.foldl_cons, List.foldl_nil]
    rfl
  rw [hst]
  refine ⟨?_, ?_, ?_⟩
  · simp only [step]
    split <;> (rw [hs₃.2.1, hs₂]; exact List.mem_cons_self)
  · simp only [step]
    split <;> exact hs₃.1
  · simp only [step]
    split
    · simp
    · rename_i hc
      simp only [hH, Bool.true_and, Option.isNone_iff_eq_none] at hc
      exact Option.isSome_iff_ne_none.mpr hc

end

/-- The leader of round `r` for a key with offset `k`: members take turns. -/
def leader (hpos : 0 < n) (k r : Nat) : Fin n := ⟨(k + r) % n, Nat.mod_lt _ hpos⟩

/-- With fewer faulty validators than members, any `n` consecutive rounds have one with an
honest leader. -/
theorem honest_leader_within_n_rounds (hpos : 0 < n) (hF : F.length < n) (k R : Nat) :
    ∃ t, t < n ∧ leader hpos k (R + t) ∉ F := by
  -- Some member is honest.
  obtain ⟨j, hj⟩ : ∃ j : Fin n, j ∉ F := by
    refine Classical.byContradiction fun hall => ?_
    have hsub : ∀ x, x ∈ List.finRange n → x ∈ F := fun x _ =>
      Classical.byContradiction fun hx => hall ⟨x, hx⟩
    have := nodup_length_le_of_subset (List.nodup_finRange n) hsub
    simp at this
    omega
  -- It leads the round `R + t` for this `t`.
  let a := (k + R) % n
  have ha : a < n := Nat.mod_lt _ hpos
  refine ⟨(j.val + n - a) % n, Nat.mod_lt _ hpos, ?_⟩
  have hlead : leader hpos k (R + (j.val + n - a) % n) = j := by
    apply Fin.ext
    simp only [leader]
    obtain ⟨q, hq⟩ : ∃ q, k + R = a + n * q := ⟨(k + R) / n, (Nat.mod_add_div _ _).symm⟩
    rw [← Nat.add_assoc, Nat.add_mod_mod, hq]
    have : a + n * q + (j.val + n - a) = j.val + n * (q + 1) := by
      rw [Nat.mul_succ]
      generalize n * q = m
      omega
    rw [this, Nat.add_mul_mod_self_left, Nat.mod_eq_of_lt j.isLt]
  rw [hlead]
  exact hj

end Liveness

/-! ## The stall, and how a round ends it

`f = 1`, `n = 4`, values `0` and `1` for one key. Validators `0` and `1` receive version `0` first,
`2` and `3` version `1`: round 0 has two votes for each, so no value has the `3` votes of a
prepare certificate, and with only round 0 the key stays open for ever. A round with an honest
leader decides it. -/

/-- The votes of round 0, split two and two. -/
def splitInputs (i : Fin 4) : List (Input 4 Nat) :=
  if i.val < 2 then [.request 0, .request 1] else [.request 1, .request 0]

theorem split_votes_no_quorum :
    (List.finRange 4).map (fun i => ((runNode 1 (fun _ => true) (splitInputs i)).prevotes)) =
      [[(0, 0)], [(0, 0)], [(0, 1)], [(0, 1)]] ∧
    ∀ i : Fin 4, (runNode 1 (fun _ => true) (splitInputs i)).decided = none := by
  refine ⟨by decide, by decide⟩

/-- After the split, a good round decides the same value at every validator. -/
theorem split_then_good_round_decides :
    let st := fun i => runNode 1 (fun _ => true) (splitInputs i)
    ∀ i : Fin 4,
      (runNode 1 (fun _ => true) (splitInputs i ++ goodRound 1 [] st 0 1 i)).decided = some 0 := by
  decide

end PSystem.Rounds
