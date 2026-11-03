import PSystem.Soundness

namespace PSystem

/-!
# Completeness of `derive` (convergence plan, phase 4)

Main results:

- `derive_complete`: if some valid execution of `events` exists, `derive`
  succeeds. The greedy choice never blocks a history that could run.
- `derive_eq_none_iff`: `derive` fails exactly when no valid execution exists.

Exchange argument. Let `σ = α ++ e :: β` be a valid run and `e` the event
the greedy loop selects (ready and executable now). Then `e :: (α ++ β)` is
also a valid run:

- No event of `α` has the sender of `e`. Otherwise the nonce of that sender
  would have advanced before `e` runs in `σ`, and `e` would not be
  executable there (`nonce_closed_form`). No conflict-freedom hypothesis
  is needed: it follows from `σ` being executable.
- Running `e` first only lowers the balance of its own sender and raises
  that of its receiver, so every event of `α` stays executable
  (`AgreeExcept`).
- After `e` and `α` the state is the same as after `α` and `e`
  (phase 2), so `β` runs unchanged.
- Readiness only depends on the set of processed ids, which only grows.

The argument does not use the minimum-id rule: any ready and executable
choice is complete. The rule only makes the choice deterministic.
-/

/-! ## Runs split over append -/

theorem executableRun_append (s : State) (xs ys : List Event) :
    ExecutableRun s (xs ++ ys) ↔
      ExecutableRun s xs ∧ ExecutableRun (ApplyEvents s xs) ys := by
  induction xs generalizing s with
  | nil => simp [ExecutableRun, ApplyEvents]
  | cons x xs ih =>
      simp only [List.cons_append, ExecutableRun, ApplyEvents, ih, and_assoc]

theorem readyRun_append (p : List EventId) (xs ys : List Event) :
    ReadyRun p (xs ++ ys) ↔
      ReadyRun p xs ∧ ReadyRun (p ++ xs.map Event.id) ys := by
  induction xs generalizing p with
  | nil => simp [ReadyRun]
  | cons x xs ih =>
      simp only [List.cons_append, ReadyRun, ih, List.map_cons,
        List.append_assoc, List.nil_append, and_assoc]

/-- Readiness only depends on which ids have been processed. -/
theorem readyRun_mono {p p' : List EventId} (hsub : ∀ id, id ∈ p → id ∈ p') :
    ∀ xs, ReadyRun p xs → ReadyRun p' xs
  | [], _ => trivial
  | x :: xs, ⟨hx, hxs⟩ => by
      refine ⟨fun id hid => hsub id (hx id hid), ?_⟩
      exact readyRun_mono (p := p ++ [x.id]) (p' := p' ++ [x.id])
        (by
          intro id hid
          simp only [List.mem_append, List.mem_singleton] at hid ⊢
          rcases hid with h | h
          · exact Or.inl (hsub id h)
          · exact Or.inr h)
        xs hxs

/-- R17's `ValidSequence` gives readiness in cons form. -/
theorem readyRun_of_validSequence {events seq : List Event}
    (h : ValidSequence events seq) : ReadyRun [] seq := by
  induction h with
  | nil => trivial
  | @append processed event _ _ _ hready ih =>
      exact (readyRun_append [] processed [event]).2
        ⟨ih, ⟨by simpa using hready, trivial⟩⟩

/-! ## Events of other senders stay executable -/

/--
`t'` agrees with `t` on every account except `X`, with at least the same
balance and the same nonce.
-/
def AgreeExcept (X : Identity) (t' t : State) : Prop :=
  ∀ id, id ≠ X → t.balance id ≤ t'.balance id ∧ t'.nonce id = t.nonce id

theorem agreeExcept_apply_self (s : State) (e : Event) :
    AgreeExcept e.sender (ApplyEvent s e) s := by
  intro id hid
  by_cases hr : id = e.receiver
  · have hrs : ¬ e.receiver = e.sender := hr ▸ hid
    subst hr
    simp [ApplyEvent, hrs]
  · simp [ApplyEvent, hid, hr]

theorem executable_of_agreeExcept {X : Identity} {t' t : State} {x : Event}
    (hx : x.sender ≠ X) (hagree : AgreeExcept X t' t) (hexec : Executable t x) :
    Executable t' x := by
  obtain ⟨hpos, hne, hbal, hnonce⟩ := hexec
  obtain ⟨hle, heq⟩ := hagree x.sender hx
  exact ⟨hpos, hne, Nat.le_trans hbal hle, heq.trans hnonce⟩

/-- Applying the same event to both states preserves `AgreeExcept`. -/
theorem agreeExcept_apply {X : Identity} {t' t : State} (x : Event)
    (hagree : AgreeExcept X t' t) :
    AgreeExcept X (ApplyEvent t' x) (ApplyEvent t x) := by
  intro id hid
  obtain ⟨hle, heq⟩ := hagree id hid
  by_cases hs : id = x.sender
  · subst hs
    simp only [ApplyEvent, ite_true]
    exact ⟨Nat.sub_le_sub_right hle _, by rw [heq]⟩
  · by_cases hr : id = x.receiver
    · subst hr
      have hs' : ¬ x.receiver = x.sender := hs
      simp only [ApplyEvent, hs', ite_true, ite_false]
      exact ⟨Nat.add_le_add_right hle _, heq⟩
    · simp only [ApplyEvent, hs, hr, ite_false]
      exact ⟨hle, heq⟩

/--
A run whose events are not sent by `X` stays executable from any state
that agrees except at `X` with at least the same balances.
-/
theorem executableRun_of_agreeExcept {X : Identity} :
    ∀ (xs : List Event) {t' t : State},
      (∀ x, x ∈ xs → x.sender ≠ X) →
      AgreeExcept X t' t →
      ExecutableRun t xs →
      ExecutableRun t' xs
  | [], _, _, _, _, _ => trivial
  | x :: xs, _, _, hsend, hagree, ⟨hexec, hrest⟩ =>
      ⟨executable_of_agreeExcept (hsend x (by simp)) hagree hexec,
        executableRun_of_agreeExcept xs
          (fun y hy => hsend y (by simp [hy]))
          (agreeExcept_apply x hagree) hrest⟩

/-! ## The exchange step -/

theorem sumBy_eq_zero {f : Event → Nat} :
    ∀ {l : List Event}, sumBy f l = 0 → ∀ x, x ∈ l → f x = 0
  | [], _, _, hx => by simp at hx
  | y :: ys, h, x, hx => by
      simp only [sumBy_cons] at h
      simp only [List.mem_cons] at hx
      rcases hx with rfl | hx
      · omega
      · exact sumBy_eq_zero (by omega) x hx

/--
If `e` is executable now and also later, after the run `α`, then no event
of `α` is sent by the sender of `e`: such an event would have advanced the
sender's nonce.
-/
theorem no_same_sender_before
    {s : State} {α : List Event} {e : Event}
    (hnow : Executable s e)
    (hlater : Executable (ApplyEvents s α) e) :
    ∀ x, x ∈ α → x.sender ≠ e.sender := by
  have hnonce := nonce_closed_form s α e.sender
  have hcount : sentCount e.sender α = 0 := by
    have h1 : s.nonce e.sender = e.nonce := hnow.2.2.2
    have h2 : (ApplyEvents s α).nonce e.sender = e.nonce := hlater.2.2.2
    -- `Nonce` is an alias of `Nat` that `omega` does not unfold.
    have h3 : s.nonce e.sender + sentCount e.sender α = s.nonce e.sender + 0 := by
      rw [← hnonce, h2, h1, Nat.add_zero]
    exact Nat.add_left_cancel h3
  intro x hx hsame
  have := sumBy_eq_zero hcount x hx
  simp [hsame] at this

/--
Exchange step: if `α ++ e :: β` is an executable run and `e` is executable
now, then `α ++ β` is an executable run after running `e` first.
-/
theorem exchange_executable
    {s : State} {α β : List Event} {e : Event}
    (hrun : ExecutableRun s (α ++ e :: β))
    (hnow : Executable s e) :
    ExecutableRun (ApplyEvent s e) (α ++ β) := by
  obtain ⟨hα, hlater, hβ⟩ :
      ExecutableRun s α ∧ Executable (ApplyEvents s α) e ∧
        ExecutableRun (ApplyEvent (ApplyEvents s α) e) β := by
    have h := (executableRun_append s α (e :: β)).1 hrun
    exact ⟨h.1, h.2.1, h.2.2⟩
  have hsend := no_same_sender_before hnow hlater
  have hα' : ExecutableRun (ApplyEvent s e) α :=
    executableRun_of_agreeExcept α hsend (agreeExcept_apply_self s e) hα
  -- After `e` then `α`, the state equals the state after `α` then `e`.
  have hfront : ExecutableRun s (e :: α) := ⟨hnow, hα'⟩
  have hback : ExecutableRun s (α ++ [e]) :=
    (executableRun_append s α [e]).2 ⟨hα, ⟨hlater, trivial⟩⟩
  have hsame : ApplyEvents s (e :: α) = ApplyEvents s (α ++ [e]) :=
    executable_runs_same_state s (List.perm_append_singleton e α).symm
      hfront hback
  have hsame' : ApplyEvents (ApplyEvent s e) α =
      ApplyEvent (ApplyEvents s α) e := by
    simpa [ApplyEvents, apply_events_append] using hsame
  refine (executableRun_append (ApplyEvent s e) α β).2 ⟨hα', ?_⟩
  rw [hsame']
  exact hβ

/-- Exchange step for readiness. -/
theorem exchange_ready
    {p : List EventId} {α β : List Event} {e : Event}
    (hready : ReadyRun p (α ++ e :: β)) :
    ReadyRun (p ++ [e.id]) (α ++ β) := by
  obtain ⟨hα, _, hβ⟩ :
      ReadyRun p α ∧ R17Ready (p ++ α.map Event.id) e ∧
        ReadyRun (p ++ α.map Event.id ++ [e.id]) β := by
    have h := (readyRun_append p α (e :: β)).1 hready
    exact ⟨h.1, h.2.1, h.2.2⟩
  refine (readyRun_append (p ++ [e.id]) α β).2 ⟨?_, ?_⟩
  · exact readyRun_mono (fun id hid => by simp [hid]) α hα
  · refine readyRun_mono ?_ β hβ
    intro id hid
    simp only [List.mem_append, List.mem_singleton] at hid ⊢
    rcases hid with (h | h) | h
    · exact Or.inl (Or.inl h)
    · exact Or.inr h
    · exact Or.inl (Or.inr h)

/-! ## Completeness of the loop -/

/--
If some executable, ready run of `remaining` exists, the loop succeeds.
-/
theorem executionOrder_complete
    (s : State) (processed : List EventId) (remaining σ : List Event)
    (hnd : (remaining.map Event.id).Nodup)
    (hperm : σ.Perm remaining)
    (hrun : ExecutableRun s σ)
    (hready : ReadyRun processed σ) :
    ∃ seq, executionOrder s processed remaining = some seq := by
  rw [executionOrder]
  split
  · exact ⟨[], rfl⟩
  · rename_i hne
    split
    · rename_i hnone
      -- The head of σ is ready and executable, so selection cannot fail.
      cases σ with
      | nil => exact False.elim (hne (List.perm_nil.mp hperm.symm))
      | cons h rest =>
          have hmem : h ∈ remaining := hperm.mem_iff.mp (by simp)
          exact False.elim
            (((selectNext_eq_none_iff processed s remaining).1 hnone)
              h hmem hready.1 hrun.1)
    · rename_i e hsel
      obtain ⟨hmem, hreadyE, hexecE, _⟩ := selectNext_spec hsel
      have hmemσ : e ∈ σ := hperm.mem_iff.mpr hmem
      obtain ⟨α, β, rfl⟩ := List.append_of_mem hmemσ
      have hpermNext : (α ++ β).Perm (dropId e.id remaining) := by
        have h1 : (e :: (α ++ β)).Perm (e :: dropId e.id remaining) :=
          (List.perm_middle.symm.trans hperm).trans (perm_cons_dropId hnd hmem)
        exact h1.cons_inv
      have hlt : (dropId e.id remaining).length < remaining.length :=
        dropId_length_lt hmem
      obtain ⟨seq, hseq⟩ := executionOrder_complete (ApplyEvent s e)
        (processed ++ [e.id]) (dropId e.id remaining) (α ++ β)
        (dropId_nodup_ids e.id hnd) hpermNext
        (exchange_executable hrun hexecE) (exchange_ready hready)
      exact ⟨e :: seq, by rw [hseq]; rfl⟩
termination_by remaining.length

/-! ## Completeness of `derive` -/

/-- If a valid execution exists, `derive` succeeds. -/
theorem derive_complete
    (s : State) (events : List Event)
    (hnd : (events.map Event.id).Nodup)
    (h : ∃ seq, ValidExecution s events seq) :
    ∃ t, derive s events = some t := by
  obtain ⟨σ, hperm, hvalid, hrun⟩ := h
  obtain ⟨seq, hseq⟩ := executionOrder_complete s [] events σ hnd hperm hrun
    (readyRun_of_validSequence hvalid)
  exact ⟨ApplyEvents s seq, by simp [derive, hseq]⟩

/-- `derive` fails exactly when no valid execution exists. -/
theorem derive_eq_none_iff
    (s : State) (events : List Event)
    (hnd : (events.map Event.id).Nodup) :
    derive s events = none ↔ ¬ ∃ seq, ValidExecution s events seq := by
  constructor
  · intro hnone hex
    obtain ⟨t, ht⟩ := derive_complete s events hnd hex
    rw [hnone] at ht
    cases ht
  · intro hno
    cases ht : derive s events with
    | none => rfl
    | some t =>
        obtain ⟨seq, hvalid, _⟩ := derive_sound s events t hnd ht
        exact False.elim (hno ⟨seq, hvalid⟩)

end PSystem
